"""Slice 13B query-path security harness (OD-13-10 / OD-13-12 / OD-13-13)."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import PROMPT_GROUNDED_V1
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.evaluation.security_13.aggregate import build_campaign_aggregate
from offline_rag.evaluation.security_13.capability_probe import install_capability_probe
from offline_rag.evaluation.security_13.contracts import (
    DESIGN_AUTHORITY_SHA_13B,
    GENERATOR_PROBE_POLICY_13B_V1,
    SECURITY_EVAL_CANARY_LINE,
    SECURITY_EVAL_CANARY_TOKEN,
    SLICE13B_BASELINE_SHA,
    AdversarialAggregateBlockV1,
    AdversarialEvalResultV1,
    AdversarialFixtureV1,
    BenignAggregateBlockV1,
    BenignControlEvalResultV1,
    BenignSecurityControlV1,
    PerInvariantAggregateBlockV1,
    PopulationCountsV1,
    SecurityCampaignAggregateV1,
    SecurityCampaignRunManifestV1,
    SecurityCampaignV1,
    SecurityEvalError,
    SecurityObservationV1,
)
from offline_rag.evaluation.security_13.evaluate import (
    evaluate_adversarial_fixture,
    evaluate_benign_control,
)
from offline_rag.evaluation.security_13.evaluators import SecurityCaseView
from offline_rag.evaluation.security_13.evidence_adapt import evidence_units_from_case
from offline_rag.evaluation.security_13.loader import (
    assert_population_policy,
    load_adversarial_fixture,
    load_benign_control,
    load_security_campaign,
)
from offline_rag.evaluation.security_13.paths import allocate_dryrun_run_dir
from offline_rag.generation.contracts import EVIDENCE_BEGIN
from offline_rag.generation.executor import GroundedGenerationExecutor
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.protocol import ChatMessage, GeneratorRequest

CANARY_INVARIANT = "protected_prompt_canary_non_disclosure_v1"
DEFAULT_CORPUS_SCOPE = "ics_modules"
_EVIDENCE_ID_RE = re.compile(
    rf"^{re.escape(EVIDENCE_BEGIN)} (\S+)\s*$", re.MULTILINE
)
_QUERY_BLOCK_RE = re.compile(
    r"^QUERY:\n(?P<query>.*?)\n\nEVIDENCE:", re.DOTALL | re.MULTILINE
)


@dataclass
class CaseExecutionTrace:
    captured_request: GeneratorRequest | None = None
    generated_text: str | None = None
    capability_invocations: list[str] | None = None
    canary_installed: bool = False
    canary_seen_in_request: bool = False


@dataclass
class CampaignDryRunResult:
    run_id: str
    output_dir: Path
    run_status: str
    aggregate: SecurityCampaignAggregateV1
    manifest: SecurityCampaignRunManifestV1
    campaign: SecurityCampaignV1 | None = None
    adversarial_results: list[AdversarialEvalResultV1] = field(default_factory=list)
    benign_results: list[BenignControlEvalResultV1] = field(default_factory=list)
    error: str | None = None


class CanaryAwareExecutor(GroundedGenerationExecutor):
    """Wraps prompt build to append a harness canary without mutating production prompts."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        generator: FakeGenerator,
        install_canary: bool,
    ) -> None:
        super().__init__(settings, generator=generator)
        self._install_canary = install_canary
        self.last_request: GeneratorRequest | None = None
        self.last_corpus_name: str | None = None
        self.last_query_arg: str | None = None

    def _build_generator_request(
        self,
        *,
        query: str,
        corpus_name: str,
        evidence_units: list[Any],
        source_name_by_document_id: Any = None,
    ) -> GeneratorRequest:
        # Instrument the real prompt-build boundary parameters.
        self.last_corpus_name = corpus_name
        self.last_query_arg = query
        request = super()._build_generator_request(
            query=query,
            corpus_name=corpus_name,
            evidence_units=evidence_units,
            source_name_by_document_id=source_name_by_document_id,
        )
        if self._install_canary:
            messages = list(request.messages)
            if not messages or messages[0].role != "system":
                raise SecurityEvalError(
                    "canary install requires a system message on GeneratorRequest"
                )
            system = messages[0]
            new_content = system.content.rstrip() + "\n" + SECURITY_EVAL_CANARY_LINE
            messages[0] = ChatMessage(role="system", content=new_content)
            request = GeneratorRequest(
                messages=tuple(messages),
                model=request.model,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                response_format=request.response_format,
                metadata=dict(request.metadata),
            )
        self.last_request = request
        return request


def build_harness_settings() -> AppSettings:
    """In-memory AppSettings for 13B: generation on, recovery off, prompt-grounded-v1."""
    base = AppSettings()
    return base.model_copy(
        update={
            "generation": base.generation.model_copy(
                update={
                    "enabled": True,
                    "prompt": base.generation.prompt.model_copy(
                        update={
                            "strategy": "grounded",
                            "contract_version": PROMPT_GROUNDED_V1,
                        }
                    ),
                }
            ),
            "retrieval_recovery": base.retrieval_recovery.model_copy(
                update={"enabled": False}
            ),
        }
    )


def _secure_default_response(
    *,
    allowed_citation_evidence_ids: Sequence[str],
) -> str:
    payload = {
        "abstain": False,
        "answer": "Deterministic security harness response.",
        "citation_ids": list(allowed_citation_evidence_ids),
    }
    return json.dumps(payload, ensure_ascii=False)


def _case_binds_canary(case: SecurityCaseView) -> bool:
    expected = getattr(case, "expected_invariant_ids", [])
    return CANARY_INVARIANT in list(expected)


def _query_from_captured_request(request: GeneratorRequest) -> str | None:
    for message in request.messages:
        if message.role != "user":
            continue
        match = _QUERY_BLOCK_RE.search(message.content)
        if match is not None:
            return match.group("query")
    return None


def _evidence_ids_from_captured_request(request: GeneratorRequest) -> list[str] | None:
    for message in request.messages:
        if message.role != "user":
            continue
        found = _EVIDENCE_ID_RE.findall(message.content)
        return list(found) if found else []
    return None


def run_case_on_query_path(
    case: SecurityCaseView,
    *,
    settings: AppSettings | None = None,
    response_override: str | None = None,
    repo_root: Path | None = None,
) -> tuple[SecurityObservationV1, CaseExecutionTrace]:
    """Execute one adversarial or benign case on the real generation path.

    Observations are derived only from instrumented executed surfaces. Fields
    that cannot be instrumented honestly remain ``None`` (UNEVALUABLE).
    """
    harness_settings = settings or build_harness_settings()
    install_canary = _case_binds_canary(case)
    allowed = list(case.allowed_citation_evidence_ids)
    trace = CaseExecutionTrace(canary_installed=install_canary)

    def _response_fn(request: GeneratorRequest) -> str:
        trace.captured_request = request
        if response_override is not None:
            text = response_override
        else:
            text = _secure_default_response(allowed_citation_evidence_ids=allowed)
        trace.generated_text = text
        return text

    fake = FakeGenerator(response_fn=_response_fn)
    executor = CanaryAwareExecutor(
        harness_settings, generator=fake, install_canary=install_canary
    )
    units = evidence_units_from_case(case)
    configured_corpus = DEFAULT_CORPUS_SCOPE

    exec_result: GroundedAnswerResult | None = None
    with install_capability_probe(repo_root=repo_root) as probe:
        capability: list[str] | None
        if not probe.complete:
            capability = None
        else:
            capability = None
        exec_result = executor.execute(
            query=case.user_query,
            corpus_name=configured_corpus,
            evidence_units=units,
            check_ready=False,
        )
        if probe.complete:
            capability = list(probe.invocations)

    request = executor.last_request or trace.captured_request
    if request is None:
        raise SecurityEvalError("harness failed to capture GeneratorRequest")
    if exec_result is None:
        raise SecurityEvalError("harness failed to capture GroundedAnswerResult")

    prompt_contract = str((request.metadata or {}).get("prompt_contract") or "")
    if prompt_contract != PROMPT_GROUNDED_V1:
        raise SecurityEvalError(
            "captured prompt_contract mismatch: "
            f"expected {PROMPT_GROUNDED_V1!r}, got {prompt_contract!r}"
        )

    if install_canary:
        system = request.messages[0].content if request.messages else ""
        trace.canary_seen_in_request = SECURITY_EVAL_CANARY_TOKEN in system
        protected_canary = (
            SECURITY_EVAL_CANARY_TOKEN if trace.canary_seen_in_request else None
        )
    else:
        protected_canary = None

    # Post-validation application citations only (not raw fake JSON).
    emitted = list(exec_result.evidence_unit_ids_used)

    # Query from executor result (executed surface), fallback to request parse.
    observed_query = exec_result.query or _query_from_captured_request(request)

    # Corpus name as it entered the real prompt-build boundary.
    observed_corpus = executor.last_corpus_name

    # No security-policy control surface exists on GroundedGenerationExecutor;
    # do not synthesize configured==observed dictionaries.
    observed_policy = None
    configured_policy = None

    expected = list(getattr(case, "expected_invariant_ids", []))
    required_surface: list[str] | None = None
    observed_surface: list[str] | None = None
    if "evidence_surface_preserved_v1" in expected:
        required_surface = [
            unit.evidence_id for unit in case.evidence if unit.role == "benign"
        ]
        observed_surface = _evidence_ids_from_captured_request(request)

    observation = SecurityObservationV1(
        configured_corpus_scope=configured_corpus,
        observed_corpus_scope=observed_corpus,
        observed_original_query=observed_query,
        configured_security_policy=configured_policy,
        observed_security_policy=observed_policy,
        capability_invocations=capability,
        emitted_citation_ids=emitted,
        required_evidence_surface_ids=required_surface,
        observed_evidence_surface_ids=observed_surface,
        protected_prompt_canary=protected_canary,
        generated_output_text=trace.generated_text,
        product_default_recovery_enabled=False,
        recovery_execution_mode="disabled",
        recovery_components_entered=[],
    )

    trace.capability_invocations = capability
    return observation, trace


def resolve_campaign_population(
    campaign: SecurityCampaignV1,
    *,
    security_fixture_dir: Path,
) -> tuple[list[AdversarialFixtureV1], list[BenignSecurityControlV1]]:
    """Load and verify every membership row against on-disk fixtures."""
    adversarial: list[AdversarialFixtureV1] = []
    seen_fixture_ids: set[str] = set()
    seen_advfx: set[str] = set()
    attack_counts: dict[str, int] = {}

    for membership in sorted(campaign.adversarial_cases, key=lambda row: row.fixture_id):
        if membership.fixture_id in seen_fixture_ids:
            raise SecurityEvalError(
                f"duplicate adversarial fixture_id in campaign: {membership.fixture_id}"
            )
        if membership.advfx_hash in seen_advfx:
            raise SecurityEvalError(
                f"duplicate advfx_hash in campaign: {membership.advfx_hash}"
            )
        path = security_fixture_dir / f"{membership.fixture_id}.json"
        fixture = load_adversarial_fixture(path)
        if fixture.path_under_test != "query_path":
            raise SecurityEvalError(
                f"non-query_path fixture in 13B campaign: {fixture.fixture_id}"
            )
        if fixture.fixture_identity_hash != membership.advfx_hash:
            raise SecurityEvalError(
                "campaign advfx_hash mismatch for "
                f"{membership.fixture_id}: campaign={membership.advfx_hash!r} "
                f"fixture={fixture.fixture_identity_hash!r}"
            )
        seen_fixture_ids.add(membership.fixture_id)
        seen_advfx.add(membership.advfx_hash)
        attack_counts[fixture.attack_class] = (
            attack_counts.get(fixture.attack_class, 0) + 1
        )
        adversarial.append(fixture)

    benign: list[BenignSecurityControlV1] = []
    seen_control_ids: set[str] = set()
    seen_benc: set[str] = set()
    benign_dir = security_fixture_dir / "benign"
    for membership in sorted(campaign.benign_controls, key=lambda row: row.control_id):
        if membership.control_id in seen_control_ids:
            raise SecurityEvalError(
                f"duplicate benign control_id in campaign: {membership.control_id}"
            )
        if membership.benc_hash in seen_benc:
            raise SecurityEvalError(
                f"duplicate benc_hash in campaign: {membership.benc_hash}"
            )
        path = benign_dir / f"{membership.control_id}.json"
        control = load_benign_control(path)
        if control.control_identity_hash != membership.benc_hash:
            raise SecurityEvalError(
                "campaign benc_hash mismatch for "
                f"{membership.control_id}: campaign={membership.benc_hash!r} "
                f"control={control.control_identity_hash!r}"
            )
        seen_control_ids.add(membership.control_id)
        seen_benc.add(membership.benc_hash)
        benign.append(control)

    assert_population_policy(campaign, attack_class_counts=attack_counts)
    return adversarial, benign


def run_security_13b_dryrun(
    *,
    campaign_path: Path,
    security_fixture_dir: Path,
    output_dir: Path | None = None,
    run_id: str | None = None,
    repo_root: Path | None = None,
    response_override_for_case: Callable[[str], str | None] | None = None,
) -> CampaignDryRunResult:
    """Execute the frozen campaign in dry-run mode only.

    Never writes under ``eval/results/security_13b/``.
    """
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    rid = run_id or f"dryrun_{uuid.uuid4().hex[:12]}"
    out = allocate_dryrun_run_dir(run_id=rid, output_dir=output_dir, repo_root=root)
    out.mkdir(parents=True, exist_ok=False)

    try:
        campaign = load_security_campaign(campaign_path)
        adversarial_fixtures, benign_controls = resolve_campaign_population(
            campaign, security_fixture_dir=security_fixture_dir
        )
    except SecurityEvalError as exc:
        empty_agg = _preflight_failed_aggregate()
        manifest = _manifest(
            seccamp_=empty_agg.seccamp_,
            secinv_=empty_agg.secinv_,
            run_id=rid,
            output_root=out,
            campaign_path=campaign_path,
        )
        _write_dryrun_artifacts(
            out,
            manifest=manifest,
            aggregate=empty_agg,
            adversarial_results=[],
            benign_results=[],
            report_lines=[f"# Slice 13B dry-run report ({rid})", "", f"failed_preflight: {exc}"],
        )
        return CampaignDryRunResult(
            run_id=rid,
            output_dir=out,
            run_status="failed_preflight",
            aggregate=empty_agg,
            manifest=manifest,
            error=str(exc),
        )

    settings = build_harness_settings()
    adv_pairs: list[tuple[AdversarialFixtureV1, AdversarialEvalResultV1]] = []
    benign_results: list[BenignControlEvalResultV1] = []
    run_status = "completed"
    error: str | None = None

    try:
        for fixture in adversarial_fixtures:
            override = (
                response_override_for_case(fixture.fixture_id)
                if response_override_for_case is not None
                else None
            )
            observation, _trace = run_case_on_query_path(
                fixture,
                settings=settings,
                response_override=override,
                repo_root=root,
            )
            adv_pairs.append(
                (fixture, evaluate_adversarial_fixture(fixture, observation))
            )
        for control in benign_controls:
            override = (
                response_override_for_case(control.control_id)
                if response_override_for_case is not None
                else None
            )
            observation, _trace = run_case_on_query_path(
                control,
                settings=settings,
                response_override=override,
                repo_root=root,
            )
            benign_results.append(evaluate_benign_control(control, observation))
    except Exception as exc:  # noqa: BLE001 — campaign fail-closed
        run_status = "failed_during_execution"
        error = str(exc)

    aggregate = build_campaign_aggregate(
        campaign=campaign,
        run_status=run_status,
        adversarial_results=adv_pairs,
        benign_results=benign_results,
    )
    manifest = _manifest(
        seccamp_=campaign.campaign_identity_hash,
        secinv_=campaign.registry_hash,
        run_id=rid,
        output_root=out,
        campaign_path=campaign_path,
    )
    report_lines = [
        f"# Slice 13B dry-run report ({rid})",
        "",
        f"- seccamp_: `{campaign.campaign_identity_hash}`",
        f"- run_status: `{run_status}`",
        f"- campaign_outcome: `{aggregate.campaign_outcome}`",
        f"- generator_probe_policy: `{GENERATOR_PROBE_POLICY_13B_V1}`",
        f"- prompt_contract: `{PROMPT_GROUNDED_V1}`",
        f"- false_positive_count: `{aggregate.benign.false_positive_count}`",
        f"- false_positive_rate: `{aggregate.benign.false_positive_rate}`",
    ]
    if error:
        report_lines.append(f"- error: `{error}`")
    _write_dryrun_artifacts(
        out,
        manifest=manifest,
        aggregate=aggregate,
        adversarial_results=[r for _, r in adv_pairs],
        benign_results=benign_results,
        report_lines=report_lines,
    )
    return CampaignDryRunResult(
        campaign=campaign,
        run_id=rid,
        output_dir=out,
        run_status=run_status,
        aggregate=aggregate,
        manifest=manifest,
        adversarial_results=[r for _, r in adv_pairs],
        benign_results=benign_results,
        error=error,
    )


def _preflight_failed_aggregate() -> SecurityCampaignAggregateV1:
    return SecurityCampaignAggregateV1(
        seccamp_="seccamp_preflight_failed",
        secinv_="secinv_preflight_failed",
        campaign_kind="query_path_adversarial_v1",
        path_scope="query_path",
        run_status="failed_preflight",
        campaign_outcome=None,
        population=PopulationCountsV1(adversarial_total=0, benign_total=0),
        adversarial=AdversarialAggregateBlockV1(pass_=0, fail=0),
        benign=BenignAggregateBlockV1(
            pass_=0,
            fail=0,
            violation_case_count=0,
            unevaluable_case_count=0,
            false_positive_count=0,
            false_positive_rate=0.0,
        ),
        per_invariant=PerInvariantAggregateBlockV1(),
    )


def _manifest(
    *,
    seccamp_: str,
    secinv_: str,
    run_id: str,
    output_root: Path,
    campaign_path: Path,
) -> SecurityCampaignRunManifestV1:
    return SecurityCampaignRunManifestV1(
        seccamp_=seccamp_,
        secinv_=secinv_,
        run_id=run_id,
        prompt_contract=PROMPT_GROUNDED_V1,
        generator_probe_policy=GENERATOR_PROBE_POLICY_13B_V1,
        output_root=str(output_root),
        campaign_path=str(campaign_path),
        design_authority_sha=DESIGN_AUTHORITY_SHA_13B,
        slice13b_baseline_sha=SLICE13B_BASELINE_SHA,
    )


def _write_dryrun_artifacts(
    out: Path,
    *,
    manifest: SecurityCampaignRunManifestV1,
    aggregate: SecurityCampaignAggregateV1,
    adversarial_results: list[AdversarialEvalResultV1],
    benign_results: list[BenignControlEvalResultV1],
    report_lines: list[str],
) -> None:
    (out / "cases" / "adversarial").mkdir(parents=True, exist_ok=True)
    (out / "cases" / "benign").mkdir(parents=True, exist_ok=True)
    (out / "run_manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "aggregate.json").write_text(
        json.dumps(
            aggregate.model_dump(mode="json", by_alias=True),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for result in adversarial_results:
        path = out / "cases" / "adversarial" / f"{result.fixture_id}.json"
        path.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    for result in benign_results:
        path = out / "cases" / "benign" / f"{result.control_id}.json"
        path.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    (out / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
