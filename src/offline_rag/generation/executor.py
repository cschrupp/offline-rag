"""GroundedGenerationExecutor — post-evidence Slice 8 generation path."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from offline_rag.config.models import AppSettings
from offline_rag.core.document_metadata import (
    DocumentMetadataError,
    resolve_document_title_v1,
)
from offline_rag.core.ids import PROMPT_GROUNDED_PROVENANCE_V2, PROMPT_GROUNDED_V1
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.domain.indexing import EvidenceUnit
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
from offline_rag.generation.prompt import (
    build_prompt_grounded_provenance_v2,
    build_prompt_grounded_v1,
)
from offline_rag.generation.prompt_evidence import PromptEvidence
from offline_rag.generation.protocol import Generator, GeneratorRequest
from offline_rag.generation.schema import parse_grounded_answer_v1
from offline_rag.generation.status import (
    describe_generation_status,
    generation_status_for_corpus,
)
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)


class GroundedGenerationError(RuntimeError):
    """Fail-closed generation execution error (configuration / unsupported)."""


class PromptProvenanceUnavailable(Exception):
    """Trusted document provenance could not be resolved for provenance-v2."""

    def __init__(
        self,
        message: str,
        *,
        failed_evidence_unit_id: str | None = None,
        failed_document_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_evidence_unit_id = failed_evidence_unit_id
        self.failed_document_id = failed_document_id


@dataclass(frozen=True, slots=True)
class GenerationContextProvenance:
    """Optional Slice 7 / retrieval provenance attached to a generation result."""

    context_config_hash: str | None = None
    dense_index_id: str | None = None
    lexical_index_id: str | None = None
    fusion_config_hash: str | None = None
    reranker_config_hash: str | None = None
    chunk_set_id: str | None = None
    context_latency_ms: int = 0
    context_breakdown: dict[str, Any] | None = None


class GroundedGenerationExecutor:
    """Execute grounded-answer generation from a fixed ``EvidenceUnit[]``.

    Does not run retrieval or context assembly. Does not score answers or judge.
    """

    def __init__(
        self,
        settings: AppSettings,
        *,
        generator: Generator | None = None,
    ) -> None:
        self.settings = settings
        if generator is not None:
            self._generator = generator
            self._owned_generator = False
        else:
            self._generator = OpenAICompatibleGenerator(settings)
            self._owned_generator = True

    def close(self) -> None:
        if self._owned_generator and hasattr(self._generator, "close"):
            self._generator.close()  # type: ignore[union-attr]

    def require_ready(self, corpus_name: str) -> None:
        status = generation_status_for_corpus(self.settings, corpus_name)
        if status == "READY":
            return
        details = describe_generation_status(self.settings, corpus_name)
        reasons = details.get("reasons") or []
        reason_text = "; ".join(str(item) for item in reasons) if reasons else "unknown"
        raise GroundedGenerationError(
            "Generation unavailable.\n"
            f"Generation status: {details.get('status')}\n"
            f"Context status:    {details.get('context_status')}\n"
            f"Reasons:           {reason_text}"
        )

    def execute(
        self,
        *,
        query: str,
        corpus_name: str,
        evidence_units: list[EvidenceUnit],
        context_provenance: GenerationContextProvenance | None = None,
        check_ready: bool = True,
    ) -> GroundedAnswerResult:
        if not query or not query.strip():
            raise GroundedGenerationError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        if check_ready:
            self.require_ready(name)

        gen = self.settings.generation
        if not gen.enabled:
            raise GroundedGenerationError("generation.enabled is false")

        gencfg = build_generation_config_hash(self.settings)
        semantics = build_generation_semantic_payload(self.settings)
        provenance = context_provenance or GenerationContextProvenance()
        total_t0 = time.perf_counter()
        query_text = query.strip()
        units = list(evidence_units)

        context_ms = int(provenance.context_latency_ms)

        if not units:
            exec_ms = int((time.perf_counter() - total_t0) * 1000)
            return self._empty_context_result(
                query=query_text,
                gencfg=gencfg,
                semantics=semantics,
                provenance=provenance,
                total_ms=context_ms + exec_ms,
            )

        prompt_t0 = time.perf_counter()
        try:
            request = self._build_generator_request(
                query=query_text,
                corpus_name=name,
                evidence_units=units,
            )
        except PromptProvenanceUnavailable as exc:
            prompt_ms = int((time.perf_counter() - prompt_t0) * 1000)
            return self._failed(
                query=query_text,
                status="generation_failed",
                failure_reason="prompt_provenance_unavailable",
                gencfg=gencfg,
                semantics=semantics,
                provenance=provenance,
                attempt_count=0,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "validation": 0,
                    "total": context_ms + prompt_ms,
                },
                extra_diagnostics={
                    "failure_stage": "prompt_provenance_resolution",
                    "failed_evidence_unit_id": exc.failed_evidence_unit_id,
                    "failed_document_id": exc.failed_document_id,
                    "error": str(exc),
                },
            )
        prompt_ms = int((time.perf_counter() - prompt_t0) * 1000)

        gen_t0 = time.perf_counter()
        try:
            response = self._generator.generate(request)
            gen_ms = int((time.perf_counter() - gen_t0) * 1000)
        except OpenAICompatibleGeneratorError as exc:
            gen_ms = int((time.perf_counter() - gen_t0) * 1000)
            return self._failed(
                query=query_text,
                status="generation_failed",
                failure_reason=exc.failure_reason,
                gencfg=gencfg,
                semantics=semantics,
                provenance=provenance,
                attempt_count=1,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": 0,
                    "total": context_ms + prompt_ms + gen_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001 - map unexpected generator errors
            gen_ms = int((time.perf_counter() - gen_t0) * 1000)
            return self._failed(
                query=query_text,
                status="generation_failed",
                failure_reason="provider_error",
                gencfg=gencfg,
                semantics=semantics,
                provenance=provenance,
                attempt_count=1,
                latency={
                    "context": context_ms,
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": 0,
                    "total": context_ms + prompt_ms + gen_ms,
                },
                extra_diagnostics={"error": str(exc)},
            )

        val_t0 = time.perf_counter()
        parsed = parse_grounded_answer_v1(response.content)
        if not parsed.ok or parsed.output is None:
            val_ms = int((time.perf_counter() - val_t0) * 1000)
            total_ms = int(provenance.context_latency_ms) + prompt_ms + gen_ms + val_ms
            return self._failed(
                query=query_text,
                status="generation_failed",
                failure_reason=parsed.failure_reason or "output_schema_invalid",
                gencfg=gencfg,
                semantics=semantics,
                provenance=provenance,
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
            total_ms = int(provenance.context_latency_ms) + prompt_ms + gen_ms + val_ms
            return GroundedAnswerResult(
                method="query",
                query=query_text,
                status="insufficient_evidence",
                answer_text=None,
                citations=[],
                abstention_reason="model_abstain",
                generator_invoked=True,
                attempt_count=1,
                generation_config_hash=gencfg,
                context_config_hash=provenance.context_config_hash,
                dense_index_id=provenance.dense_index_id,
                lexical_index_id=provenance.lexical_index_id,
                fusion_config_hash=provenance.fusion_config_hash,
                reranker_config_hash=provenance.reranker_config_hash,
                effective_generation_semantics=semantics,
                diagnostics={
                    "abstention_reason": "model_abstain",
                    "generator_invoked": True,
                    "attempt_count": 1,
                    "usage": response.usage,
                    "latency_ms": {
                        "context": int(provenance.context_latency_ms),
                        "prompt_assembly": prompt_ms,
                        "generation": gen_ms,
                        "validation": val_ms,
                        "total": total_ms,
                        "context_breakdown": provenance.context_breakdown,
                    },
                },
                metadata={
                    "chunk_set_id": provenance.chunk_set_id,
                    "selected_endpoint": gen.base_url,
                    "selected_model": gen.model,
                },
            )

        invalid = validate_citation_membership(output.citation_ids, units)
        val_ms = int((time.perf_counter() - val_t0) * 1000)
        total_ms = int(provenance.context_latency_ms) + prompt_ms + gen_ms + val_ms
        if invalid:
            return self._failed(
                query=query_text,
                status="citation_invalid",
                failure_reason=None,
                gencfg=gencfg,
                semantics=semantics,
                provenance=provenance,
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

        citations = resolve_citations(output.citation_ids, units)
        return GroundedAnswerResult(
            method="query",
            query=query_text,
            status="answered",
            answer_text=output.answer,
            citations=citations,
            generator_invoked=True,
            attempt_count=1,
            generation_config_hash=gencfg,
            context_config_hash=provenance.context_config_hash,
            dense_index_id=provenance.dense_index_id,
            lexical_index_id=provenance.lexical_index_id,
            fusion_config_hash=provenance.fusion_config_hash,
            reranker_config_hash=provenance.reranker_config_hash,
            effective_generation_semantics=semantics,
            diagnostics={
                "generator_invoked": True,
                "attempt_count": 1,
                "usage": response.usage,
                "latency_ms": {
                    "context": int(provenance.context_latency_ms),
                    "prompt_assembly": prompt_ms,
                    "generation": gen_ms,
                    "validation": val_ms,
                    "total": total_ms,
                    "context_breakdown": provenance.context_breakdown,
                },
            },
            metadata={
                "chunk_set_id": provenance.chunk_set_id,
                "selected_endpoint": gen.base_url,
                "selected_model": gen.model,
            },
        )

    def _prompt_contract(self) -> str:
        return self.settings.generation.prompt.contract_version

    def _load_source_name_by_document_id(self, corpus_name: str) -> dict[str, str]:
        corpus_path = corpus_state_path(self.settings.paths.corpora, corpus_name)
        if not corpus_path.exists():
            raise PromptProvenanceUnavailable(
                f"corpus state missing for provenance resolution: {corpus_name}"
            )
        try:
            corpus_state = load_corpus_state(corpus_path)
        except Exception as exc:
            raise PromptProvenanceUnavailable(
                f"failed to load corpus state for provenance resolution: {exc}"
            ) from exc
        manifest_path = (
            self.settings.paths.manifests / Path(corpus_state.current_manifest).name
        )
        if not manifest_path.exists():
            raise PromptProvenanceUnavailable(
                f"missing corpus manifest for provenance resolution: "
                f"{corpus_state.current_manifest}"
            )
        try:
            corpus_manifest = load_corpus_manifest(manifest_path)
        except Exception as exc:
            raise PromptProvenanceUnavailable(
                f"failed to load corpus manifest for provenance resolution: {exc}"
            ) from exc
        return {
            entry.document_id: entry.source_name for entry in corpus_manifest.documents
        }

    def _resolve_document_titles(
        self,
        *,
        evidence_units: list[EvidenceUnit],
        source_name_by_document_id: dict[str, str],
    ) -> dict[str, str]:
        titles: dict[str, str] = {}
        for unit in evidence_units:
            document_id = unit.document_id
            if document_id in titles:
                continue
            if document_id not in source_name_by_document_id:
                raise PromptProvenanceUnavailable(
                    f"document_id not found in authoritative corpus metadata: "
                    f"{document_id}",
                    failed_evidence_unit_id=unit.evidence_unit_id,
                    failed_document_id=document_id,
                )
            source_name = source_name_by_document_id[document_id]
            if source_name is None or not str(source_name).strip():
                raise PromptProvenanceUnavailable(
                    f"authoritative source_name missing/blank for "
                    f"document_id={document_id}",
                    failed_evidence_unit_id=unit.evidence_unit_id,
                    failed_document_id=document_id,
                )
            try:
                titles[document_id] = resolve_document_title_v1(str(source_name))
            except DocumentMetadataError as exc:
                raise PromptProvenanceUnavailable(
                    str(exc),
                    failed_evidence_unit_id=unit.evidence_unit_id,
                    failed_document_id=document_id,
                ) from exc
        return titles

    def _adapt_prompt_evidence(
        self,
        *,
        corpus_name: str,
        evidence_units: list[EvidenceUnit],
    ) -> list[PromptEvidence]:
        source_names = self._load_source_name_by_document_id(corpus_name)
        titles = self._resolve_document_titles(
            evidence_units=evidence_units,
            source_name_by_document_id=source_names,
        )
        adapted: list[PromptEvidence] = []
        for unit in evidence_units:
            adapted.append(
                PromptEvidence(
                    evidence_unit_id=unit.evidence_unit_id,
                    document_title=titles[unit.document_id],
                    section_path=tuple(unit.section_path),
                    text=unit.text,
                )
            )
        return adapted

    def _build_generator_request(
        self,
        *,
        query: str,
        corpus_name: str,
        evidence_units: list[EvidenceUnit],
    ) -> GeneratorRequest:
        gen = self.settings.generation
        contract = self._prompt_contract()
        if contract == PROMPT_GROUNDED_V1:
            return build_prompt_grounded_v1(
                query=query,
                evidence_units=evidence_units,
                model=gen.model,
                temperature=float(gen.temperature),
                max_output_tokens=int(gen.max_output_tokens),
            )
        if contract == PROMPT_GROUNDED_PROVENANCE_V2:
            prompt_evidence = self._adapt_prompt_evidence(
                corpus_name=corpus_name,
                evidence_units=evidence_units,
            )
            return build_prompt_grounded_provenance_v2(
                query=query,
                evidence=prompt_evidence,
                model=gen.model,
                temperature=float(gen.temperature),
                max_output_tokens=int(gen.max_output_tokens),
            )
        raise GroundedGenerationError(f"unsupported prompt_contract: {contract}")

    def _empty_context_result(
        self,
        *,
        query: str,
        gencfg: str,
        semantics: dict[str, Any],
        provenance: GenerationContextProvenance,
        total_ms: int,
    ) -> GroundedAnswerResult:
        gen = self.settings.generation
        return GroundedAnswerResult(
            method="query",
            query=query,
            status="insufficient_evidence",
            answer_text=None,
            citations=[],
            abstention_reason="empty_context",
            generator_invoked=False,
            attempt_count=0,
            generation_config_hash=gencfg,
            context_config_hash=provenance.context_config_hash,
            dense_index_id=provenance.dense_index_id,
            lexical_index_id=provenance.lexical_index_id,
            fusion_config_hash=provenance.fusion_config_hash,
            reranker_config_hash=provenance.reranker_config_hash,
            effective_generation_semantics=semantics,
            diagnostics={
                "abstention_reason": "empty_context",
                "generator_invoked": False,
                "attempt_count": 0,
                "latency_ms": {
                    "context": int(provenance.context_latency_ms),
                    "prompt_assembly": 0,
                    "generation": 0,
                    "validation": 0,
                    "total": total_ms,
                    "context_breakdown": provenance.context_breakdown,
                },
            },
            metadata={
                "chunk_set_id": provenance.chunk_set_id,
                "selected_endpoint": gen.base_url,
                "selected_model": gen.model,
            },
        )

    def _failed(
        self,
        *,
        query: str,
        status: str,
        failure_reason: str | None,
        gencfg: str,
        semantics: dict[str, Any],
        provenance: GenerationContextProvenance,
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
                "context_breakdown": provenance.context_breakdown,
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
            context_config_hash=provenance.context_config_hash,
            dense_index_id=provenance.dense_index_id,
            lexical_index_id=provenance.lexical_index_id,
            fusion_config_hash=provenance.fusion_config_hash,
            reranker_config_hash=provenance.reranker_config_hash,
            effective_generation_semantics=semantics,
            diagnostics=diagnostics,
            metadata={
                "chunk_set_id": provenance.chunk_set_id,
                "selected_endpoint": self.settings.generation.base_url,
                "selected_model": self.settings.generation.model,
            },
        )
