"""Slice 12C-2 authoritative measure-once orchestration + persistence.

Composes the accepted 12C-1 harness. Does not redesign prepare/evaluate/aggregate
semantics. One shared HybridRerankContextAssembler for Stage A and Stage B.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.context.status import context_status_for_corpus
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.evaluation.generation_semantic.cohort import load_cohort_map
from offline_rag.evaluation.gold import LoadedGoldDataset, load_gold_dataset
from offline_rag.evaluation.recovery_12c.binding import (
    require_frozen_adjudication_cohort_map,
)
from offline_rag.evaluation.recovery_12c.conclusion import conclude_recovery_eval
from offline_rag.evaluation.recovery_12c.contracts import (
    FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C,
    FROZEN_GOLD_DATASET_ID_12C,
    RecoveryEvalAggregateV1,
    RecoveryEvalError,
    TriggerCensusV1,
)
from offline_rag.evaluation.recovery_12c.harness import (
    PreparedRecoveryEvalBatch,
    PreparedRecoveryEvalCase,
    aggregate_authoritative_recovery_eval,
    evaluate_prepared_batch,
    prepare_authoritative_recovery_eval,
    recompute_authoritative_receval_identity,
)
from offline_rag.evaluation.recovery_12c.identity import (
    build_recovery_eval_identity_hash,
)
from offline_rag.evaluation.recovery_12c.measure_once_contracts import (
    ACCEPTED_HARNESS_SHA_12C,
    AUTHORITY_BASELINE_SHA_12C,
    RecoveryEvalCensusStopAggregateV1,
    RecoveryEvalPreparedCaseV1,
    RecoveryEvalRunManifestV1,
    RetrievalStackIdentityV1,
    RewriterManifestIdentityV1,
)
from offline_rag.evaluation.recovery_12c.preflight import (
    require_authoritative_recovery_preflight,
)
from offline_rag.evaluation.recovery_12c.recompute import (
    gold_judgments_from_case,
    recompute_ranking_metrics,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.hybrid.status import describe_hybrid_status
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
from offline_rag.recovery.lineage import RecoveryLineageV1, lineage_stack_equal
from offline_rag.recovery.rewrite_provider import OpenAICompatibleRecoveryRewriter
from offline_rag.rerank.config_hash import build_reranker_config_hash

FROZEN_GOLD_PATH_12C = Path(
    "data/corpora/ics_modules/gold_authoring/gold/"
    "authorrun_b28d88f64054491a837cb4a144cbe056"
)
FROZEN_COHORT_MAP_PATH_12C = Path(
    "eval/fixtures/sufficiency/"
    "gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172"
    "_adjudication_cohort_map_v1.json"
)
FROZEN_CORPUS_NAME_12C = "ics_modules"
DEFAULT_RESULTS_PARENT = Path("eval/results/recovery_12c")

RunStatus = Literal[
    "completed",
    "stopped_not_evaluable",
    "failed_before_stage_a",
    "failed_after_stage_a",
]


@dataclass(frozen=True, slots=True)
class Recovery12CRunResult:
    """Library return value; CLI owns presentation / exit codes."""

    run_status: RunStatus
    result_root: Path | None
    recovery_eval_identity_hash: str | None
    rewriter_config_hash: str | None
    stage_b_executed: bool
    conclusion: str | None
    human_trigger_count: int | None = None
    assistant_trigger_count: int | None = None
    rewrite_call_count: int = 0
    recovery_retrieval_attempt_count: int = 0
    failure_message: str | None = None


class SharedInitialAssemblerAdapter:
    """Stage-A adapter: assemble_initial → shared production assembler."""

    def __init__(
        self,
        assembler: HybridRerankContextAssembler,
        *,
        corpus_name: str,
    ) -> None:
        self._assembler = assembler
        self._corpus_name = corpus_name

    def assemble_initial(self, query: str) -> HybridRerankContextResult:
        return self._assembler.assemble(query=query, corpus_name=self._corpus_name)


def inject_recovery_rewriter_api_key_from_environ(
    settings: AppSettings,
    *,
    environ: dict[str, str] | None = None,
) -> AppSettings:
    """Copy settings with rewriter.api_key from OFFLINE_RAG_LLM_API_KEY."""
    env = environ if environ is not None else os.environ
    api_key = str(env.get("OFFLINE_RAG_LLM_API_KEY", "")).strip()
    if not api_key:
        raise RecoveryEvalError(
            "OFFLINE_RAG_LLM_API_KEY is required for 12C-2 "
            "(inject into retrieval_recovery.rewriter.api_key before Stage A)"
        )
    rewriter = settings.retrieval_recovery.rewriter.model_copy(
        update={"api_key": api_key}
    )
    recovery = settings.retrieval_recovery.model_copy(update={"rewriter": rewriter})
    return settings.model_copy(update={"retrieval_recovery": recovery})


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_expected_stack(
    settings: AppSettings,
    gold: LoadedGoldDataset,
    *,
    corpus_name: str,
) -> RetrievalStackIdentityV1:
    if context_status_for_corpus(settings, corpus_name) != "READY":
        raise RecoveryEvalError(f"context stack not READY for corpus {corpus_name!r}")
    hybrid = describe_hybrid_status(settings, corpus_name)
    if hybrid.get("status") != "READY":
        raise RecoveryEvalError(f"hybrid stack not READY for corpus {corpus_name!r}")
    dense_id = hybrid.get("dense_index_id")
    lexical_id = hybrid.get("lexical_index_id")
    active_chunk = hybrid.get("active_chunk_set_id")
    if not dense_id or not lexical_id or not active_chunk:
        raise RecoveryEvalError("unable to resolve dense/lexical/chunk-set identities")
    if gold.meta.chunk_set_id != active_chunk:
        raise RecoveryEvalError(
            "Gold chunk_set_id does not match active corpus chunk set: "
            f"gold={gold.meta.chunk_set_id!r} active={active_chunk!r}"
        )
    state_path = corpus_state_path(settings.paths.corpora, corpus_name)
    if not state_path.exists():
        raise RecoveryEvalError(f"missing corpus state at {state_path}")
    corpus_state = load_corpus_state(state_path)
    corpus_id = corpus_state.current_corpus_id
    if gold.meta.corpus_id is not None and gold.meta.corpus_id != corpus_id:
        raise RecoveryEvalError(
            "Gold corpus_id does not match corpus state: "
            f"gold={gold.meta.corpus_id!r} state={corpus_id!r}"
        )
    counter = make_token_counter(settings)
    return RetrievalStackIdentityV1(
        corpus_id=corpus_id,
        chunk_set_id=str(active_chunk),
        dense_index_id=str(dense_id),
        lexical_index_id=str(lexical_id),
        fusion_config_hash=build_fusion_config_hash(settings),
        reranker_config_hash=build_reranker_config_hash(settings),
        context_config_hash=build_context_config_hash(settings, token_counter=counter),
    )


def _stack_as_lineage(
    stack: RetrievalStackIdentityV1, *, query: str
) -> RecoveryLineageV1:
    return RecoveryLineageV1(
        corpus_id=stack.corpus_id,
        chunk_set_id=stack.chunk_set_id,
        dense_index_id=stack.dense_index_id,
        lexical_index_id=stack.lexical_index_id,
        fusion_config_hash=stack.fusion_config_hash,
        reranker_config_hash=stack.reranker_config_hash,
        context_config_hash=stack.context_config_hash,
        query=query,
    )


def _validate_frozen_population(
    *,
    gold: LoadedGoldDataset,
    cohort_map_path: Path,
) -> tuple[object, str]:
    if gold.dataset_id != FROZEN_GOLD_DATASET_ID_12C:
        raise RecoveryEvalError(
            "12C-2 requires frozen Gold dataset ID "
            f"{FROZEN_GOLD_DATASET_ID_12C}; got {gold.dataset_id}"
        )
    if len(gold.cases) != 22:
        raise RecoveryEvalError(
            f"12C-2 requires exactly 22 Gold cases; got {len(gold.cases)}"
        )
    cohort_map = load_cohort_map(cohort_map_path)
    digest = require_frozen_adjudication_cohort_map(cohort_map)
    if digest != FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C:
        raise RecoveryEvalError("cohort-map identity mismatch against frozen 12C hash")
    human = sum(1 for c in cohort_map.cases if c.label_cohort == "human_reviewed")
    assistant = sum(1 for c in cohort_map.cases if c.label_cohort == "assistant_only")
    if human != 16 or assistant != 6:
        raise RecoveryEvalError(
            f"frozen cohort counts must be 16 human / 6 assistant; got {human}/{assistant}"
        )
    return cohort_map, digest


def _require_shared_observed_stack(
    batch: PreparedRecoveryEvalBatch,
    expected: RetrievalStackIdentityV1,
) -> RetrievalStackIdentityV1:
    if not batch.cases:
        raise RecoveryEvalError("prepared batch is empty")
    expected_lineage = _stack_as_lineage(expected, query="__expected__")
    for prepared in batch.cases:
        lineage = prepared.initial_observation.lineage
        if lineage is None:
            raise RecoveryEvalError(
                f"prepared case {prepared.case.id!r} missing initial lineage"
            )
        if not lineage_stack_equal(expected_lineage, lineage):
            raise RecoveryEvalError(
                "Stage-A retrieval stack diverged from preflight expectation for "
                f"case {prepared.case.id!r}"
            )
    # Also require mutual equality across cases.
    reference = batch.cases[0].initial_observation.lineage
    assert reference is not None
    for prepared in batch.cases[1:]:
        other = prepared.initial_observation.lineage
        assert other is not None
        if not lineage_stack_equal(reference, other):
            raise RecoveryEvalError(
                f"Stage-A stack mismatch between cases (at {prepared.case.id!r})"
            )
    return expected


def prepared_case_from_runtime(
    prepared: PreparedRecoveryEvalCase,
) -> RecoveryEvalPreparedCaseV1:
    judgments = gold_judgments_from_case(prepared.case)
    positives = sorted(j.chunk_id for j in judgments if int(j.relevance) > 0)
    ranking = recompute_ranking_metrics(
        case_id=prepared.case.id,
        query=prepared.original_query,
        judgments=judgments,
        ranked_chunk_ids=prepared.initial_observation.ranked_anchor_chunk_ids,
    )
    return RecoveryEvalPreparedCaseV1(
        case_id=prepared.case.id,
        adjudication_cohort=prepared.adjudication_cohort,
        original_query=prepared.original_query,
        gold_judgments=list(judgments),
        gold_positive_chunk_ids=positives,
        initial=prepared.initial_observation,
        triggered=prepared.triggered,
        initial_ranking=ranking,
    )


def build_census_stop_aggregate(
    *,
    batch: PreparedRecoveryEvalBatch,
    census: TriggerCensusV1,
    rewriter_config_hash: str,
    evaluation_identity_hash: str,
    retrieval_lineage: RetrievalStackIdentityV1,
) -> RecoveryEvalCensusStopAggregateV1:
    if census.human_trigger_count != 0:
        raise RecoveryEvalError("census-stop aggregate requires T_H == 0")
    conclusion = conclude_recovery_eval(
        human_trigger_count=0,
        gold_positive_recovery_count=0,
        unsupported_recovery_count=0,
        recovery_failure_count=0,
        happy_path_divergence_count=0,
    )
    human_n = sum(1 for p in batch.cases if p.adjudication_cohort == "human_reviewed")
    assistant_n = sum(
        1 for p in batch.cases if p.adjudication_cohort == "assistant_only"
    )
    return RecoveryEvalCensusStopAggregateV1(
        total_case_count=len(batch.cases),
        human_reviewed_count=human_n,
        assistant_only_count=assistant_n,
        human_stage_a_trigger_count=census.human_trigger_count,
        assistant_stage_a_trigger_count=census.assistant_trigger_count,
        conclusion=conclusion,
        gold_dataset_id=batch.gold_dataset_id or FROZEN_GOLD_DATASET_ID_12C,
        cohort_map_identity_hash=batch.cohort_map_identity_hash
        or FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C,
        prepared_case_set_hash=batch.prepared_case_set_hash or "",
        rewriter_config_hash=rewriter_config_hash,
        evaluation_identity_hash=evaluation_identity_hash,
        retrieval_lineage=retrieval_lineage,
    )


def _write_json(path: Path, payload: object) -> None:
    if hasattr(payload, "model_dump_json"):
        text = payload.model_dump_json(indent=2)  # type: ignore[union-attr]
    else:
        text = json.dumps(payload, indent=2, sort_keys=True)
    atomic_write_text(path, text if text.endswith("\n") else text + "\n")


def _write_jsonl(path: Path, rows: Sequence[object]) -> None:
    lines: list[str] = []
    for row in rows:
        if hasattr(row, "model_dump_json"):
            lines.append(row.model_dump_json())  # type: ignore[union-attr]
        else:
            lines.append(json.dumps(row, sort_keys=True))
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def _rewriter_manifest(settings: AppSettings) -> RewriterManifestIdentityV1:
    rw = settings.retrieval_recovery.rewriter
    return RewriterManifestIdentityV1(
        provider=rw.provider,
        adapter_contract=rw.adapter_contract,
        base_url=rw.base_url,
        model=rw.model,
        network_policy=rw.network_policy,
        prompt_contract=rw.prompt_contract,
        output_contract=rw.output_contract,
    )


def _render_report(
    *,
    run_status: RunStatus,
    stage_b_executed: bool,
    census: TriggerCensusV1 | None,
    conclusion: str | None,
    aggregate: object | None,
    receval: str | None,
    rrwcfg: str | None,
) -> str:
    lines = [
        "# Slice 12C-2 authoritative recovery measure-once report",
        "",
        f"- run_status: `{run_status}`",
        f"- stage_b_executed: `{str(stage_b_executed).lower()}`",
        f"- authority_baseline_sha: `{AUTHORITY_BASELINE_SHA_12C}`",
        f"- accepted_harness_sha: `{ACCEPTED_HARNESS_SHA_12C}`",
        f"- gold_dataset_id: `{FROZEN_GOLD_DATASET_ID_12C}`",
        f"- cohort_map_identity_hash: `{FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C}`",
        f"- rrwcfg_: `{rrwcfg}`",
        f"- receval_: `{receval}`",
        f"- conclusion: `{conclusion}`",
        "",
    ]
    if census is not None:
        lines.extend(
            [
                "## Trigger census (Stage A)",
                "",
                (
                    f"- T_H (human): **{census.human_trigger_count}** "
                    f"`{list(census.human_trigger_case_ids)}`"
                ),
                (
                    f"- T_A (assistant): **{census.assistant_trigger_count}** "
                    f"`{list(census.assistant_trigger_case_ids)}`"
                ),
                f"- not_evaluable: `{census.not_evaluable}`",
                f"- stop_reason: `{census.stop_reason}`",
                "",
            ]
        )
    if isinstance(aggregate, RecoveryEvalCensusStopAggregateV1):
        lines.extend(
            [
                "## Census-stop aggregate",
                "",
                f"- human_reviewed_count: {aggregate.human_reviewed_count}",
                f"- assistant_only_count: {aggregate.assistant_only_count}",
                f"- human_stage_a_trigger_count: {aggregate.human_stage_a_trigger_count}",
                (
                    "- assistant_stage_a_trigger_count: "
                    f"{aggregate.assistant_stage_a_trigger_count}"
                ),
                (
                    "- measured_recovery_case_count: "
                    f"{aggregate.measured_recovery_case_count}"
                ),
                f"- rewrite_call_count: {aggregate.rewrite_call_count}",
                (
                    "- recovery_retrieval_attempt_count: "
                    f"{aggregate.recovery_retrieval_attempt_count}"
                ),
                "",
            ]
        )
    elif isinstance(aggregate, RecoveryEvalAggregateV1):
        h = aggregate.human
        a = aggregate.assistant
        lines.extend(
            [
                "## Human-reviewed (authoritative)",
                "",
                f"- total_case_count: {h.total_case_count}",
                f"- trigger_count: {h.trigger_count}",
                f"- initial_sufficient_count: {h.initial_sufficient_count}",
                f"- gold_positive_recovery_count: {h.gold_positive_recovery_count}",
                f"- unsupported_recovery_count: {h.unsupported_recovery_count}",
                f"- still_insufficient_count: {h.still_insufficient_count}",
                f"- recovery_failure_count: {h.recovery_failure_count}",
                f"- no_op_rewrite_count: {h.no_op_rewrite_count}",
                f"- happy_path_divergence_count: {h.happy_path_divergence_count}",
                "",
                "## Assistant-only (descriptive only)",
                "",
                f"- total_case_count: {a.total_case_count}",
                f"- trigger_count: {a.trigger_count}",
                f"- gold_positive_recovery_count: {a.gold_positive_recovery_count}",
                f"- unsupported_recovery_count: {a.unsupported_recovery_count}",
                f"- still_insufficient_count: {a.still_insufficient_count}",
                f"- recovery_failure_count: {a.recovery_failure_count}",
                f"- no_op_rewrite_count: {a.no_op_rewrite_count}",
                f"- happy_path_divergence_count: {a.happy_path_divergence_count}",
                "",
            ]
        )
    lines.extend(
        [
            "## Policy / method notes",
            "",
            (
                "- `retrieval_recovery.enabled=false` remains the product default in "
                "`config/base.yaml`; this evaluation-only overlay does not promote recovery."
            ),
            "- No generation / LLM judge was used as promotion truth.",
            "- No LangGraph was used.",
            (
                "- Scientific limitation: the current Gold set has no authoritative "
                "genuinely-unanswerable negative population, so 12C does not estimate "
                "the false-recovery rate on unanswerable questions."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def run_authoritative_recovery_eval(
    settings: AppSettings,
    *,
    gold_path: Path = FROZEN_GOLD_PATH_12C,
    cohort_map_path: Path = FROZEN_COHORT_MAP_PATH_12C,
    corpus_name: str = FROZEN_CORPUS_NAME_12C,
    results_parent: Path = DEFAULT_RESULTS_PARENT,
) -> Recovery12CRunResult:
    """Execute exactly one authoritative 12C measure-once evaluation."""
    started_at = _utc_now()
    stage_a_started = False
    result_root: Path | None = None
    rrwcfg: str | None = None
    receval: str | None = None
    census: TriggerCensusV1 | None = None
    aggregate: object | None = None
    conclusion: str | None = None
    rewrite_calls = 0
    recovery_retrievals = 0
    stage_b_executed = False
    expected_stack: RetrievalStackIdentityV1 | None = None
    batch: PreparedRecoveryEvalBatch | None = None

    assembler: HybridRerankContextAssembler | None = None
    rewriter: OpenAICompatibleRecoveryRewriter | None = None

    try:
        if (
            settings.retrieval_recovery.rewriter.api_key is None
            or not str(settings.retrieval_recovery.rewriter.api_key).strip()
        ):
            raise RecoveryEvalError(
                "recovery rewriter api_key must be injected before "
                "run_authoritative_recovery_eval"
            )

        gold = load_gold_dataset(gold_path)
        cohort_map, _cohort_hash = _validate_frozen_population(
            gold=gold, cohort_map_path=cohort_map_path
        )
        if corpus_name != FROZEN_CORPUS_NAME_12C:
            raise RecoveryEvalError(
                f"12C-2 requires corpus_name={FROZEN_CORPUS_NAME_12C!r}; "
                f"got {corpus_name!r}"
            )

        rrwcfg = require_authoritative_recovery_preflight(settings)
        expected_stack = _resolve_expected_stack(
            settings, gold, corpus_name=corpus_name
        )
        receval = build_recovery_eval_identity_hash(
            gold_dataset_id=gold.dataset_id,
            cohort_map=cohort_map,
            corpus_id=expected_stack.corpus_id,
            chunk_set_id=expected_stack.chunk_set_id,
            dense_index_id=expected_stack.dense_index_id,
            lexical_index_id=expected_stack.lexical_index_id,
            fusion_config_hash=expected_stack.fusion_config_hash,
            reranker_config_hash=expected_stack.reranker_config_hash,
            context_config_hash=expected_stack.context_config_hash,
            rewriter_config_hash=rrwcfg,
        )
        result_root = results_parent / receval
        if result_root.exists():
            raise RecoveryEvalError(
                f"authoritative result root already exists (no overwrite): {result_root}"
            )
        result_root.mkdir(parents=True, exist_ok=False)

        assembler = HybridRerankContextAssembler(settings)
        rewriter = OpenAICompatibleRecoveryRewriter(settings)
        initial_adapter = SharedInitialAssemblerAdapter(
            assembler, corpus_name=corpus_name
        )

        stage_a_started = True
        batch = prepare_authoritative_recovery_eval(
            gold=gold,
            cohort_map=cohort_map,
            initial_assembler=initial_adapter,
        )
        observed_stack = _require_shared_observed_stack(batch, expected_stack)
        recomputed = recompute_authoritative_receval_identity(
            batch, rewriter_config_hash=rrwcfg
        )
        if recomputed != receval:
            raise RecoveryEvalError(
                "receval_ recomputed from prepared batch does not match "
                f"preflight identity: expected {receval}, got {recomputed}"
            )
        census = batch.census
        _write_json(result_root / "trigger_census.json", census)

        if census.human_trigger_count == 0:
            prepared_rows = [
                prepared_case_from_runtime(p)
                for p in sorted(batch.cases, key=lambda item: item.case.id)
            ]
            _write_jsonl(result_root / "prepared_cases.jsonl", prepared_rows)
            aggregate = build_census_stop_aggregate(
                batch=batch,
                census=census,
                rewriter_config_hash=rrwcfg,
                evaluation_identity_hash=receval,
                retrieval_lineage=observed_stack,
            )
            conclusion = aggregate.conclusion.value
            _write_json(result_root / "aggregate.json", aggregate)
            manifest = RecoveryEvalRunManifestV1(
                authority_baseline_sha=AUTHORITY_BASELINE_SHA_12C,
                accepted_harness_sha=ACCEPTED_HARNESS_SHA_12C,
                run_status="stopped_not_evaluable",
                gold_dataset_id=batch.gold_dataset_id,
                cohort_map_identity_hash=batch.cohort_map_identity_hash,
                prepared_case_set_hash=batch.prepared_case_set_hash,
                recovery_rewriter_config_hash=rrwcfg,
                recovery_eval_identity_hash=receval,
                retrieval_lineage=observed_stack,
                rewriter=_rewriter_manifest(settings),
                stage_b_executed=False,
                case_record_status="not_applicable_stage_b_not_executed",
                case_record_artifact=None,
                prepared_case_artifact="prepared_cases.jsonl",
                started_at=started_at,
                completed_at=_utc_now(),
            )
            _write_json(result_root / "run_manifest.json", manifest)
            report = _render_report(
                run_status="stopped_not_evaluable",
                stage_b_executed=False,
                census=census,
                conclusion=conclusion,
                aggregate=aggregate,
                receval=receval,
                rrwcfg=rrwcfg,
            )
            atomic_write_text(result_root / "report.md", report)
            return Recovery12CRunResult(
                run_status="stopped_not_evaluable",
                result_root=result_root,
                recovery_eval_identity_hash=receval,
                rewriter_config_hash=rrwcfg,
                stage_b_executed=False,
                conclusion=conclusion,
                human_trigger_count=census.human_trigger_count,
                assistant_trigger_count=census.assistant_trigger_count,
                rewrite_call_count=0,
                recovery_retrieval_attempt_count=0,
            )

        # Stage B — T_H > 0
        stage_b_executed = True
        records = evaluate_prepared_batch(
            batch,
            recovery_settings=settings,
            recovery_assembler=assembler,
            rewriter=rewriter,
            corpus_name=corpus_name,
            stop_if_not_evaluable=False,
        )
        records_sorted = sorted(records, key=lambda item: item.case_id)
        if len(records_sorted) != len(batch.cases):
            raise RecoveryEvalError(
                "Stage B must emit exactly one record per prepared case"
            )
        rewrite_calls = sum(r.rewrite_call_count for r in records_sorted)
        recovery_retrievals = sum(
            r.recovery_retrieval_attempt_count for r in records_sorted
        )
        _write_jsonl(result_root / "case_records.jsonl", records_sorted)
        aggregate = aggregate_authoritative_recovery_eval(
            batch,
            records_sorted,
            recovery_settings=settings,
        )
        if aggregate.evaluation_identity_hash != receval:
            raise RecoveryEvalError(
                "authoritative aggregate receval_ mismatch against preflight identity"
            )
        conclusion = aggregate.conclusion.value
        _write_json(result_root / "aggregate.json", aggregate)
        manifest = RecoveryEvalRunManifestV1(
            authority_baseline_sha=AUTHORITY_BASELINE_SHA_12C,
            accepted_harness_sha=ACCEPTED_HARNESS_SHA_12C,
            run_status="completed",
            gold_dataset_id=batch.gold_dataset_id,
            cohort_map_identity_hash=batch.cohort_map_identity_hash,
            prepared_case_set_hash=batch.prepared_case_set_hash,
            recovery_rewriter_config_hash=rrwcfg,
            recovery_eval_identity_hash=receval,
            retrieval_lineage=observed_stack,
            rewriter=_rewriter_manifest(settings),
            stage_b_executed=True,
            case_record_status="complete",
            case_record_artifact="case_records.jsonl",
            prepared_case_artifact=None,
            started_at=started_at,
            completed_at=_utc_now(),
        )
        _write_json(result_root / "run_manifest.json", manifest)
        report = _render_report(
            run_status="completed",
            stage_b_executed=True,
            census=census,
            conclusion=conclusion,
            aggregate=aggregate,
            receval=receval,
            rrwcfg=rrwcfg,
        )
        atomic_write_text(result_root / "report.md", report)
        return Recovery12CRunResult(
            run_status="completed",
            result_root=result_root,
            recovery_eval_identity_hash=receval,
            rewriter_config_hash=rrwcfg,
            stage_b_executed=True,
            conclusion=conclusion,
            human_trigger_count=census.human_trigger_count,
            assistant_trigger_count=census.assistant_trigger_count,
            rewrite_call_count=rewrite_calls,
            recovery_retrieval_attempt_count=recovery_retrievals,
        )
    except Exception as exc:  # noqa: BLE001 — persist any Stage A/B failure honestly
        status: RunStatus = (
            "failed_after_stage_a" if stage_a_started else "failed_before_stage_a"
        )
        message = str(exc)
        # Avoid leaking secrets if a misbehaving component embeds them.
        api_key = settings.retrieval_recovery.rewriter.api_key
        if api_key and api_key in message:
            message = message.replace(api_key, "<redacted>")
        if result_root is not None and result_root.exists():
            try:
                fail_manifest = RecoveryEvalRunManifestV1(
                    authority_baseline_sha=AUTHORITY_BASELINE_SHA_12C,
                    accepted_harness_sha=ACCEPTED_HARNESS_SHA_12C,
                    run_status=status,
                    gold_dataset_id=FROZEN_GOLD_DATASET_ID_12C,
                    cohort_map_identity_hash=FROZEN_ADJUDICATION_COHORT_MAP_HASH_12C,
                    prepared_case_set_hash=(
                        batch.prepared_case_set_hash if batch is not None else None
                    ),
                    recovery_rewriter_config_hash=rrwcfg,
                    recovery_eval_identity_hash=receval,
                    retrieval_lineage=expected_stack,
                    rewriter=_rewriter_manifest(settings),
                    stage_b_executed=stage_b_executed,
                    case_record_status="failed",
                    case_record_artifact=None,
                    prepared_case_artifact=None,
                    started_at=started_at,
                    completed_at=_utc_now(),
                    failure_message=message,
                )
                _write_json(result_root / "run_manifest.json", fail_manifest)
                if (
                    census is not None
                    and not (result_root / "trigger_census.json").exists()
                ):
                    _write_json(result_root / "trigger_census.json", census)
                report = _render_report(
                    run_status=status,
                    stage_b_executed=stage_b_executed,
                    census=census,
                    conclusion=conclusion,
                    aggregate=aggregate,
                    receval=receval,
                    rrwcfg=rrwcfg,
                )
                report += f"\n## Failure\n\n```\n{message}\n```\n"
                atomic_write_text(result_root / "report.md", report)
            except Exception:  # noqa: BLE001, S110 — best-effort failure persistence
                pass
        return Recovery12CRunResult(
            run_status=status,
            result_root=result_root,
            recovery_eval_identity_hash=receval,
            rewriter_config_hash=rrwcfg,
            stage_b_executed=stage_b_executed,
            conclusion=conclusion,
            human_trigger_count=(
                census.human_trigger_count if census is not None else None
            ),
            assistant_trigger_count=(
                census.assistant_trigger_count if census is not None else None
            ),
            rewrite_call_count=rewrite_calls,
            recovery_retrieval_attempt_count=recovery_retrievals,
            failure_message=message,
        )
    finally:
        if rewriter is not None:
            rewriter.close()
        if assembler is not None:
            assembler.close()
