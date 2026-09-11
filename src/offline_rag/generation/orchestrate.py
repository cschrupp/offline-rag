"""GroundedAnswerOrchestrator — public Slice 8 query path."""

from __future__ import annotations

import time
from typing import Any

from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.generation.citations import (
    resolve_citations,
    validate_citation_membership,
)
from offline_rag.generation.config_hash import (
    build_generation_config_hash,
    build_generation_semantic_payload,
)
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    OpenAICompatibleGeneratorError,
)
from offline_rag.generation.prompt import build_prompt_grounded_v1
from offline_rag.generation.protocol import Generator
from offline_rag.generation.schema import parse_grounded_answer_v1
from offline_rag.generation.status import (
    describe_generation_status,
    generation_status_for_corpus,
)
from offline_rag.ingestion.discovery import validate_corpus_name


class GroundedAnswerError(RuntimeError):
    pass


class GroundedAnswerOrchestrator:
    """Compose context assembly + grounded generation into query results."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        context_assembler: HybridRerankContextAssembler | None = None,
        generator: Generator | None = None,
    ) -> None:
        self.settings = settings
        self._assembler = context_assembler or HybridRerankContextAssembler(settings)
        self._owned_assembler = context_assembler is None
        if generator is not None:
            self._generator = generator
            self._owned_generator = False
        else:
            self._generator = OpenAICompatibleGenerator(settings)
            self._owned_generator = True

    def close(self) -> None:
        if self._owned_assembler:
            self._assembler.close()
        if self._owned_generator and hasattr(self._generator, "close"):
            self._generator.close()  # type: ignore[union-attr]

    def _require_ready(self, corpus_name: str) -> None:
        status = generation_status_for_corpus(self.settings, corpus_name)
        if status == "READY":
            return
        details = describe_generation_status(self.settings, corpus_name)
        reasons = details.get("reasons") or []
        reason_text = "; ".join(str(item) for item in reasons) if reasons else "unknown"
        raise GroundedAnswerError(
            "Generation unavailable.\n"
            f"Generation status: {details.get('status')}\n"
            f"Context status:    {details.get('context_status')}\n"
            f"Reasons:           {reason_text}"
        )

    def answer(self, *, query: str, corpus_name: str = "default") -> GroundedAnswerResult:
        if not query or not query.strip():
            raise GroundedAnswerError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        self._require_ready(name)

        gen = self.settings.generation
        if not gen.enabled:
            raise GroundedAnswerError("generation.enabled is false")

        gencfg = build_generation_config_hash(self.settings)
        semantics = build_generation_semantic_payload(self.settings)
        total_t0 = time.perf_counter()

        context_t0 = time.perf_counter()
        try:
            context = self._assembler.assemble(query=query.strip(), corpus_name=name)
        except HybridRerankContextError as exc:
            raise GroundedAnswerError(str(exc)) from exc
        context_ms = int((time.perf_counter() - context_t0) * 1000)

        self._assert_context_invariants(context)

        if not context.evidence_units:
            total_ms = int((time.perf_counter() - total_t0) * 1000)
            return GroundedAnswerResult(
                method="query",
                query=query.strip(),
                status="insufficient_evidence",
                answer_text=None,
                citations=[],
                abstention_reason="empty_context",
                generator_invoked=False,
                attempt_count=0,
                generation_config_hash=gencfg,
                context_config_hash=context.context_config_hash,
                dense_index_id=context.dense_index_id,
                lexical_index_id=context.lexical_index_id,
                fusion_config_hash=context.fusion_config_hash,
                reranker_config_hash=context.reranker_config_hash,
                effective_generation_semantics=semantics,
                diagnostics={
                    "abstention_reason": "empty_context",
                    "generator_invoked": False,
                    "attempt_count": 0,
                    "latency_ms": {
                        "context": context_ms,
                        "prompt_assembly": 0,
                        "generation": 0,
                        "validation": 0,
                        "total": total_ms,
                        "context_breakdown": (context.metadata or {}).get("latency_ms"),
                    },
                },
                metadata={
                    "chunk_set_id": (context.metadata or {}).get("chunk_set_id"),
                    "selected_endpoint": gen.base_url,
                    "selected_model": gen.model,
                },
            )

        prompt_t0 = time.perf_counter()
        request = build_prompt_grounded_v1(
            query=query.strip(),
            evidence_units=list(context.evidence_units),
            model=gen.model,
            temperature=float(gen.temperature),
            max_output_tokens=int(gen.max_output_tokens),
        )
        prompt_ms = int((time.perf_counter() - prompt_t0) * 1000)

        gen_t0 = time.perf_counter()
        try:
            response = self._generator.generate(request)
            gen_ms = int((time.perf_counter() - gen_t0) * 1000)
        except OpenAICompatibleGeneratorError as exc:
            gen_ms = int((time.perf_counter() - gen_t0) * 1000)
            total_ms = int((time.perf_counter() - total_t0) * 1000)
            return self._failed(
                query=query.strip(),
                status="generation_failed",
                failure_reason=exc.failure_reason,
                context=context,
                gencfg=gencfg,
                semantics=semantics,
                attempt_count=1,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": 0,
                    "total": total_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001 - map unexpected generator errors
            gen_ms = int((time.perf_counter() - gen_t0) * 1000)
            total_ms = int((time.perf_counter() - total_t0) * 1000)
            return self._failed(
                query=query.strip(),
                status="generation_failed",
                failure_reason="provider_error",
                context=context,
                gencfg=gencfg,
                semantics=semantics,
                attempt_count=1,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": 0,
                    "total": total_ms,
                },
                extra_diagnostics={"error": str(exc)},
            )

        val_t0 = time.perf_counter()
        parsed = parse_grounded_answer_v1(response.content)
        if not parsed.ok or parsed.output is None:
            val_ms = int((time.perf_counter() - val_t0) * 1000)
            total_ms = int((time.perf_counter() - total_t0) * 1000)
            return self._failed(
                query=query.strip(),
                status="generation_failed",
                failure_reason=parsed.failure_reason or "output_schema_invalid",
                context=context,
                gencfg=gencfg,
                semantics=semantics,
                attempt_count=1,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": val_ms,
                    "total": total_ms,
                },
                raw_model_output=response.content,
                usage=response.usage,
            )

        output = parsed.output
        if output.abstain:
            val_ms = int((time.perf_counter() - val_t0) * 1000)
            total_ms = int((time.perf_counter() - total_t0) * 1000)
            return GroundedAnswerResult(
                method="query",
                query=query.strip(),
                status="insufficient_evidence",
                answer_text=None,
                citations=[],
                abstention_reason="model_abstain",
                generator_invoked=True,
                attempt_count=1,
                generation_config_hash=gencfg,
                context_config_hash=context.context_config_hash,
                dense_index_id=context.dense_index_id,
                lexical_index_id=context.lexical_index_id,
                fusion_config_hash=context.fusion_config_hash,
                reranker_config_hash=context.reranker_config_hash,
                effective_generation_semantics=semantics,
                diagnostics={
                    "abstention_reason": "model_abstain",
                    "generator_invoked": True,
                    "attempt_count": 1,
                    "usage": response.usage,
                    "latency_ms": {
                        "context": context_ms,
                        "prompt_assembly": prompt_ms,
                        "generation": gen_ms,
                        "validation": val_ms,
                        "total": total_ms,
                        "context_breakdown": (context.metadata or {}).get("latency_ms"),
                    },
                },
                metadata={
                    "chunk_set_id": (context.metadata or {}).get("chunk_set_id"),
                    "selected_endpoint": gen.base_url,
                    "selected_model": gen.model,
                },
            )

        invalid = validate_citation_membership(output.citation_ids, list(context.evidence_units))
        val_ms = int((time.perf_counter() - val_t0) * 1000)
        total_ms = int((time.perf_counter() - total_t0) * 1000)
        if invalid:
            return self._failed(
                query=query.strip(),
                status="citation_invalid",
                failure_reason=None,
                context=context,
                gencfg=gencfg,
                semantics=semantics,
                attempt_count=1,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": val_ms,
                    "total": total_ms,
                },
                raw_model_output=response.content,
                usage=response.usage,
                extra_diagnostics={"invalid_citation_ids": invalid},
            )

        citations = resolve_citations(output.citation_ids, list(context.evidence_units))
        return GroundedAnswerResult(
            method="query",
            query=query.strip(),
            status="answered",
            answer_text=output.answer,
            citations=citations,
            generator_invoked=True,
            attempt_count=1,
            generation_config_hash=gencfg,
            context_config_hash=context.context_config_hash,
            dense_index_id=context.dense_index_id,
            lexical_index_id=context.lexical_index_id,
            fusion_config_hash=context.fusion_config_hash,
            reranker_config_hash=context.reranker_config_hash,
            effective_generation_semantics=semantics,
            diagnostics={
                "generator_invoked": True,
                "attempt_count": 1,
                "usage": response.usage,
                "latency_ms": {
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": val_ms,
                    "total": total_ms,
                    "context_breakdown": (context.metadata or {}).get("latency_ms"),
                },
            },
            metadata={
                "chunk_set_id": (context.metadata or {}).get("chunk_set_id"),
                "selected_endpoint": gen.base_url,
                "selected_model": gen.model,
            },
        )

    def _assert_context_invariants(self, context: HybridRerankContextResult) -> None:
        joined = "\n\n".join(unit.text for unit in context.evidence_units)
        if context.assembled_text != joined:
            raise GroundedAnswerError(
                "Slice 7 context invariant violated: assembled_text does not match evidence units"
            )
        if not context.evidence_units and (
            context.assembled_text != "" or context.context_token_count != 0
        ):
            raise GroundedAnswerError("Slice 7 empty-context invariant violated")

    def _failed(
        self,
        *,
        query: str,
        status: str,
        failure_reason: str | None,
        context: HybridRerankContextResult,
        gencfg: str,
        semantics: dict[str, Any],
        attempt_count: int,
        latency: dict[str, Any],
        raw_model_output: str | None = None,
        usage: dict[str, Any] | None = None,
        extra_diagnostics: dict[str, Any] | None = None,
    ) -> GroundedAnswerResult:
        diagnostics: dict[str, Any] = {
            "generator_invoked": attempt_count > 0,
            "attempt_count": attempt_count,
            "latency_ms": {
                **latency,
                "context_breakdown": (context.metadata or {}).get("latency_ms"),
            },
        }
        if failure_reason:
            diagnostics["generation_failure_reason"] = failure_reason
        if usage:
            diagnostics["usage"] = usage
        if raw_model_output is not None:
            diagnostics["raw_model_output"] = raw_model_output
        if extra_diagnostics:
            diagnostics.update(extra_diagnostics)
        return GroundedAnswerResult(
            method="query",
            query=query,
            status=status,  # type: ignore[arg-type]
            answer_text=None,
            citations=[],
            generation_failure_reason=failure_reason,
            generator_invoked=attempt_count > 0,
            attempt_count=attempt_count,
            generation_config_hash=gencfg,
            context_config_hash=context.context_config_hash,
            dense_index_id=context.dense_index_id,
            lexical_index_id=context.lexical_index_id,
            fusion_config_hash=context.fusion_config_hash,
            reranker_config_hash=context.reranker_config_hash,
            effective_generation_semantics=semantics,
            diagnostics=diagnostics,
            metadata={
                "chunk_set_id": (context.metadata or {}).get("chunk_set_id"),
                "selected_endpoint": self.settings.generation.base_url,
                "selected_model": self.settings.generation.model,
            },
        )
