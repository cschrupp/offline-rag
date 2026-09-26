"""GroundedAnswerOrchestrator — public Slice 8 query path."""

from __future__ import annotations

import time

from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.generation.executor import (
    GenerationContextProvenance,
    GroundedGenerationError,
    GroundedGenerationExecutor,
    PromptProvenanceUnavailable,
)
from offline_rag.generation.protocol import Generator
from offline_rag.generation.status import (
    describe_generation_status,
    generation_status_for_corpus,
)
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.sufficiency.policy import (
    SufficiencyPolicyError,
    evaluate_runtime_sufficiency,
)

# Re-export for existing imports / tests.
__all__ = [
    "GroundedAnswerError",
    "GroundedAnswerOrchestrator",
    "PromptProvenanceUnavailable",
]


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
        executor: GroundedGenerationExecutor | None = None,
    ) -> None:
        self.settings = settings
        self._assembler = context_assembler or HybridRerankContextAssembler(settings)
        self._owned_assembler = context_assembler is None
        if executor is not None:
            if generator is not None:
                raise GroundedAnswerError("pass either generator or executor, not both")
            self._executor = executor
            self._owned_executor = False
        elif generator is not None:
            self._executor = GroundedGenerationExecutor(settings, generator=generator)
            self._owned_executor = True
        else:
            self._executor = GroundedGenerationExecutor(settings)
            self._owned_executor = True

    def close(self) -> None:
        if self._owned_assembler:
            self._assembler.close()
        if self._owned_executor:
            self._executor.close()

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

    def answer(
        self, *, query: str, corpus_name: str = "default"
    ) -> GroundedAnswerResult:
        if not query or not query.strip():
            raise GroundedAnswerError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        self._require_ready(name)

        gen = self.settings.generation
        if not gen.enabled:
            raise GroundedAnswerError("generation.enabled is false")

        context_t0 = time.perf_counter()
        try:
            context = self._assembler.assemble(query=query.strip(), corpus_name=name)
        except HybridRerankContextError as exc:
            raise GroundedAnswerError(str(exc)) from exc
        context_ms = int((time.perf_counter() - context_t0) * 1000)

        self._assert_context_invariants(context)

        # Slice 11C: formal sufficiency-v1 gate after assembly, before generation.
        # Authorized rule set: empty_context => insufficient only.
        try:
            evaluate_runtime_sufficiency(
                self.settings, evidence_units=context.evidence_units
            )
        except SufficiencyPolicyError as exc:
            raise GroundedAnswerError(str(exc)) from exc

        provenance = GenerationContextProvenance(
            context_config_hash=context.context_config_hash,
            dense_index_id=context.dense_index_id,
            lexical_index_id=context.lexical_index_id,
            fusion_config_hash=context.fusion_config_hash,
            reranker_config_hash=context.reranker_config_hash,
            chunk_set_id=(context.metadata or {}).get("chunk_set_id"),
            context_latency_ms=context_ms,
            context_breakdown=(context.metadata or {}).get("latency_ms"),
        )
        try:
            return self._executor.execute(
                query=query.strip(),
                corpus_name=name,
                evidence_units=list(context.evidence_units),
                context_provenance=provenance,
                check_ready=False,
            )
        except GroundedGenerationError as exc:
            raise GroundedAnswerError(str(exc)) from exc

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
