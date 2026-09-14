"""Question proposal orchestration (Slice 9B)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import new_execution_id
from offline_rag.gold_authoring.adapter import (
    AuthoringAdapterError,
    OpenAICompatibleAuthoringAdapter,
)
from offline_rag.gold_authoring.chunk_access import (
    ChunkAccessError,
    load_current_corpus_chunk_snapshot,
)
from offline_rag.gold_authoring.config_hash import build_authoring_config_hash
from offline_rag.gold_authoring.context import (
    ProposalContextError,
    build_proposal_source_context,
)
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    ProposalAttempt,
    ProposalAttemptStatus,
    ProposalFailureReason,
    ProposalPipelineProvenance,
    SilverCase,
    SourceSeed,
)
from offline_rag.gold_authoring.persist import (
    default_authoring_run_path,
    write_authoring_run,
)
from offline_rag.gold_authoring.privacy import (
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
    normalize_authoring_endpoint,
)
from offline_rag.gold_authoring.prompt import question_proposal_system_prompt
from offline_rag.gold_authoring.quality import apply_proposal_quality_gates
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness
from offline_rag.gold_authoring.sampling import (
    SamplingError,
    build_eligible_population,
    sample_source_seeds,
)
from offline_rag.gold_authoring.schema import (
    QuestionProposalParseError,
    parse_question_proposal_v1,
)


class ProposePreRunError(RuntimeError):
    """Valid proposal run could not start (CLI exit 2)."""


@dataclass
class ProposeJobResult:
    exit_code: int
    run: GoldAuthoringRun | None = None
    output_path: Path | None = None
    message: str = ""
    failure_reason_counts: Counter[str] = field(default_factory=Counter)


def _map_adapter_failure(reason: str) -> tuple[ProposalAttemptStatus, ProposalFailureReason]:
    mapping: dict[str, tuple[ProposalAttemptStatus, ProposalFailureReason]] = {
        "timeout": (ProposalAttemptStatus.FAILED_TRANSPORT, ProposalFailureReason.TIMEOUT),
        "transport_error": (
            ProposalAttemptStatus.FAILED_TRANSPORT,
            ProposalFailureReason.TRANSPORT_ERROR,
        ),
        "http_error": (
            ProposalAttemptStatus.FAILED_TRANSPORT,
            ProposalFailureReason.HTTP_ERROR,
        ),
        "authentication_error": (
            ProposalAttemptStatus.FAILED_TRANSPORT,
            ProposalFailureReason.AUTHENTICATION_ERROR,
        ),
        "redirect_not_allowed": (
            ProposalAttemptStatus.FAILED_TRANSPORT,
            ProposalFailureReason.REDIRECT_NOT_ALLOWED,
        ),
        "empty_response": (
            ProposalAttemptStatus.FAILED_RESPONSE,
            ProposalFailureReason.EMPTY_RESPONSE,
        ),
    }
    return mapping.get(
        reason,
        (ProposalAttemptStatus.FAILED_TRANSPORT, ProposalFailureReason.TRANSPORT_ERROR),
    )


def run_gold_propose(
    settings: AppSettings,
    *,
    corpus_name: str,
    count: int = 20,
    seed: int = 0,
    output: Path | None = None,
    force: bool = False,
    adapter: OpenAICompatibleAuthoringAdapter | None = None,
) -> ProposeJobResult:
    # --- Pre-run readiness / privacy ---
    readiness = evaluate_authoring_readiness(settings)
    if not readiness.ready:
        raise ProposePreRunError(
            f"Authoring NOT READY: {', '.join(readiness.reason_codes) or 'unknown'}"
        )
    try:
        authorized = authorize_authoring_endpoint(settings)
        effective_endpoint = authorized.endpoint
    except AuthoringPrivacyError as exc:
        raise ProposePreRunError(f"authoring endpoint unauthorized: {exc}") from exc

    # --- Resolve CURRENT chunk snapshot ---
    try:
        snapshot = load_current_corpus_chunk_snapshot(
            settings, corpus_name=corpus_name
        )
    except ChunkAccessError as exc:
        raise ProposePreRunError(str(exc)) from exc

    population = build_eligible_population(snapshot.chunks)
    if not population:
        raise ProposePreRunError("no eligible source children in CURRENT ChunkSet")

    try:
        selected = sample_source_seeds(population, count=count, seed=seed)
    except SamplingError as exc:
        raise ProposePreRunError(str(exc)) from exc

    authoring_run_id = new_execution_id(prefix="authorrun")
    output_path = output or default_authoring_run_path(
        settings,
        corpus_name=corpus_name,
        authoring_run_id=authoring_run_id,
    )
    if output_path.exists() and not force:
        raise ProposePreRunError(
            f"output already exists (pass --force to overwrite): {output_path}"
        )

    owned_adapter = adapter is None
    active = adapter or OpenAICompatibleAuthoringAdapter(settings)
    system_prompt = question_proposal_system_prompt()
    attempts: list[ProposalAttempt] = []
    cases: list[SilverCase] = []
    accepted_queries: list[str] = []
    reason_counts: Counter[str] = Counter()

    try:
        for item in selected:
            source_seed = SourceSeed(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_title=None,
                section_path=list(item.section_path),
            )
            try:
                context = build_proposal_source_context(
                    item,
                    source_name=snapshot.source_name_by_document_id.get(
                        item.document_id
                    ),
                )
            except ProposalContextError:
                attempt = ProposalAttempt(
                    source_seed=source_seed,
                    status=ProposalAttemptStatus.FAILED_CONTEXT,
                    failure_reason=ProposalFailureReason.PROPOSAL_CONTEXT_UNAVAILABLE,
                    draft_case_id=None,
                    proposal=None,
                )
                attempts.append(attempt)
                reason_counts[str(attempt.failure_reason)] += 1
                continue

            source_seed = SourceSeed(
                chunk_id=context.chunk_id,
                document_id=context.document_id,
                document_title=context.document_title,
                section_path=list(context.section_path),
            )
            user_message = context.render_user_message()

            try:
                content = active.propose(
                    system_prompt=system_prompt,
                    user_content=user_message,
                )
            except AuthoringAdapterError as exc:
                status, reason = _map_adapter_failure(exc.failure_reason)
                attempt = ProposalAttempt(
                    source_seed=source_seed,
                    status=status,
                    failure_reason=reason,
                )
                attempts.append(attempt)
                reason_counts[str(reason)] += 1
                continue

            try:
                proposal = parse_question_proposal_v1(content)
            except QuestionProposalParseError as exc:
                reason = (
                    ProposalFailureReason.INVALID_JSON
                    if exc.reason == "invalid_json"
                    else ProposalFailureReason.EMPTY_RESPONSE
                    if exc.reason == "empty_response"
                    else ProposalFailureReason.SCHEMA_INVALID
                )
                attempt = ProposalAttempt(
                    source_seed=source_seed,
                    status=ProposalAttemptStatus.FAILED_SCHEMA,
                    failure_reason=reason,
                )
                attempts.append(attempt)
                reason_counts[str(reason)] += 1
                continue

            gate = apply_proposal_quality_gates(
                proposal,
                seed_text=context.text,
                accepted_queries=accepted_queries,
            )
            if not gate.ok:
                assert gate.reason is not None
                attempt = ProposalAttempt(
                    source_seed=source_seed,
                    status=ProposalAttemptStatus.REJECTED_QUALITY,
                    failure_reason=gate.reason,
                    proposal=proposal,
                )
                attempts.append(attempt)
                reason_counts[str(gate.reason)] += 1
                continue

            draft_case_id = new_execution_id(prefix="draft")
            case = SilverCase(
                draft_case_id=draft_case_id,
                proposed_query=proposal.query,
                proposed_category=proposal.category,
                proposed_tags=list(proposal.tags),
                proposal_rationale=proposal.rationale,
                source_seed=source_seed,
            )
            cases.append(case)
            accepted_queries.append(proposal.query)
            attempts.append(
                ProposalAttempt(
                    source_seed=source_seed,
                    status=ProposalAttemptStatus.SUCCEEDED,
                    failure_reason=None,
                    draft_case_id=draft_case_id,
                    proposal=proposal,
                )
            )
    finally:
        if owned_adapter:
            active.close()

    run = GoldAuthoringRun(
        schema_version="offline-rag-gold-authoring-v1",
        authoring_run_id=authoring_run_id,
        authorcfg_id=build_authoring_config_hash(settings),
        network_policy=settings.authoring.network_policy,
        effective_endpoint=effective_endpoint
        or normalize_authoring_endpoint(settings.authoring.base_url),
        corpus_id=snapshot.corpus_id,
        corpus_name=snapshot.corpus_name,
        chunk_set_id=snapshot.chunk_set_id,
        created_at=datetime.now(UTC),
        proposal_pipeline=ProposalPipelineProvenance(),
        sampling_seed=int(seed),
        requested_count=int(count),
        selected_chunk_ids=[item.chunk_id for item in selected],
        eligible_population_count=len(population),
        attempts=attempts,
        cases=cases,
    )

    try:
        write_authoring_run(output_path, run)
    except OSError as exc:
        return ProposeJobResult(
            exit_code=1,
            run=run,
            output_path=None,
            message=f"failed to persist authoring run: {exc}",
            failure_reason_counts=reason_counts,
        )

    exit_code = 0 if run.successful_count > 0 else 1
    return ProposeJobResult(
        exit_code=exit_code,
        run=run,
        output_path=output_path,
        message="Gold proposal run completed.",
        failure_reason_counts=reason_counts,
    )
