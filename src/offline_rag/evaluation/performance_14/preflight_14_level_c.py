"""Fail-closed Level-C execution-readiness preflight (definition / readiness only).

Consumes the accepted Level-C suite/config freeze. Does not authorize execution,
mutate the freeze, create ``perfrun_`` artifacts, run warm-ups, or perform
inference.

Provider ``/v1/models`` contact occurs only when ``provider_probe="require"``.
Default ``provider_probe="skip"`` performs zero network calls and never claims
``execution_ready=True``.

Returned ``LevelCPreflightContext.runtime_settings`` is sanitized
(``generation.api_key is None``). Secret-bearing settings exist only transiently
for the provider probe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.config.loader import ConfigError, load_dotenv, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import (
    build_context_config_hash,
    build_context_semantic_payload,
)
from offline_rag.dense.provision import (
    EmbeddingReadiness,
    resolve_embedding_model_dir,
    validate_embedding_artifacts,
)
from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceMachineProfileV1,
    PerformancePreflightRecordV1,
)
from offline_rag.evaluation.performance_14.machine import (
    capture_machine_profile_with_id,
)
from offline_rag.evaluation.performance_14.paths import reserved_results_root
from offline_rag.evaluation.performance_14.preflight import (
    PreflightAccumulator,
    assert_case_membership,
    assert_paired_comparison_invariant,
    assert_protocol_counts,
    assert_suite_identity,
    assert_treatment_only_config_delta,
    capture_working_tree_state,
    resolve_executing_sha,
    resolve_repo_root,
)
from offline_rag.evaluation.performance_14.preflight_14c import (
    HYBRID_RERANK_SETTINGS_YAMLS,
    HYBRID_SETTINGS_YAMLS,
    assert_index_and_config_pins,
)
from offline_rag.evaluation.performance_14.resources import (
    observe_ram_rss_bytes,
    observe_vram,
)
from offline_rag.evaluation.performance_14.suite_14_level_c import (
    COLD_WARM_LEVEL_C,
    EXECUTION_ORDER_CONTRACT_LEVEL_C,
    EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
    EXPECTED_TIMEOUT_SECONDS_LEVEL_C,
    GENERATION_MAX_OUTPUT_TOKENS_LEVEL_C,
    GENERATION_MODEL_LEVEL_C,
    GENERATION_PROMPT_CONTRACT_LEVEL_C,
    GENERATION_PROMPT_STRATEGY_LEVEL_C,
    GENERATION_PROVIDER_LEVEL_C,
    GENERATION_TEMPERATURE_LEVEL_C,
    INSTRUMENTATION_AUTHORITY_LEVEL_C,
    MEASURED_REPETITIONS_LEVEL_C,
    QUERY_IDS_LEVEL_C,
    VARIANT_HYBRID_RERANK_CONTEXT_GENERATION,
    WARMUP_COUNT_LEVEL_C,
    build_suite_plan_level_c,
    case_ids_level_c,
    effective_config_id_level_c,
    load_frozen_suite_artifact_level_c,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    GOLD_DATASET_ID_14C,
    GOLD_RELATIVE_PATH_14C,
    assert_gold_semantic_identity_14c,
)
from offline_rag.generation.config_hash import (
    build_generation_config_hash,
    build_generation_semantic_payload,
)
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    OpenAICompatibleGeneratorError,
    endpoint_authorized,
    normalize_endpoint,
)
from offline_rag.generation.protocol import GeneratorProbeResult

ProviderProbeMode = Literal["skip", "require"]

FREEZE_AUTHORITY_LEVEL_C = "f3ff6de00d90ebae24639d1569ef0f91b25b3c65"

LOCKED_PERFSUITE_LEVEL_C = (
    "perfsuite_d9241ed2cad9473e399ae30d875729c8d2b1faf65580457fe2a872d75ca924b0"
)
LOCKED_PERFCFG_LEVEL_C = (
    "perfcfg_a26a0fb336905dfa681c6cfe96721cf1fd446da64004336156f0336420025a25"
)
LOCKED_GENCFG_LEVEL_C = (
    "gencfg_d6b98a84f20887142dbb56a20e1b7533f6006304442efc017bb80a8fa2feb4d3"
)
LOCKED_CTXCFG_LEVEL_C = (
    "ctxcfg_b1742f41ecc03defbcf7c4e270fe22b4aa72db4a1af2c02a70d5560cd2ac8876"
)

_MIN_DISK_FREE_BYTES = 256 * 1024 * 1024

ProviderProbeFn = Callable[[AppSettings], GeneratorProbeResult]


def assert_freeze_authority_reachable(repo_root: Path) -> None:
    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", FREEZE_AUTHORITY_LEVEL_C, "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise Performance14Error(
            f"accepted Level-C suite-freeze authority {FREEZE_AUTHORITY_LEVEL_C} "
            "is not an ancestor of HEAD"
        )


def assert_working_tree_clean_for_level_c(repo_root: Path) -> None:
    state, detail = capture_working_tree_state(repo_root)
    if state != "clean":
        raise Performance14Error(
            "Level-C execution readiness requires a clean working tree; "
            f"got {state}: {detail}"
        )


def build_level_c_runtime_environment(
    repo_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> dict[str, str]:
    """Build one copied effective environment for all Level-C readiness loads.

    Precedence: supplied/process env wins; ``.env`` fills only missing keys.
    Never mutates the caller's ``os.environ``.
    """
    runtime_env: MutableMapping[str, str] = dict(
        environ if environ is not None else os.environ
    )
    env_file = (
        Path(dotenv_path) if dotenv_path is not None else (repo_root / ".env")
    )
    try:
        load_dotenv(env_file, environ=runtime_env)
    except OSError as exc:
        raise Performance14Error(
            f"failed to load runtime .env from {env_file}: {exc}"
        ) from exc
    return dict(runtime_env)


def _sanitize_config_load_error(
    exc: BaseException,
    *,
    api_key: str | None = None,
) -> str:
    detail = str(exc)
    if api_key and api_key in detail:
        detail = detail.replace(api_key, "<redacted>")
    return f"runtime configuration invalid: {type(exc).__name__}: {detail}"


def load_level_c_runtime_settings(
    repo_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
    runtime_env: Mapping[str, str] | None = None,
) -> AppSettings:
    """Load effective Level-C base runtime settings (may include secrets)."""
    env = (
        dict(runtime_env)
        if runtime_env is not None
        else build_level_c_runtime_environment(
            repo_root, environ=environ, dotenv_path=dotenv_path
        )
    )
    try:
        return load_settings(
            yaml_paths=[repo_root / "config" / "base.yaml"],
            environ=env,
        )
    except (ConfigError, OSError) as exc:
        raise Performance14Error(
            _sanitize_config_load_error(exc, api_key=env.get("OFFLINE_RAG_LLM_API_KEY"))
        ) from exc


def load_level_c_hybrid_settings(
    repo_root: Path,
    *,
    runtime_env: Mapping[str, str],
) -> AppSettings:
    """Load hybrid retrieval settings using the same runtime environment."""
    paths = [repo_root / rel for rel in HYBRID_SETTINGS_YAMLS]
    try:
        return load_settings(yaml_paths=paths, environ=runtime_env)
    except (ConfigError, OSError) as exc:
        raise Performance14Error(
            _sanitize_config_load_error(
                exc, api_key=runtime_env.get("OFFLINE_RAG_LLM_API_KEY")
            )
        ) from exc


def load_level_c_hybrid_rerank_settings(
    repo_root: Path,
    *,
    runtime_env: Mapping[str, str],
) -> AppSettings:
    """Load hybrid+rerank settings using the same runtime environment."""
    paths = [repo_root / rel for rel in HYBRID_RERANK_SETTINGS_YAMLS]
    try:
        return load_settings(yaml_paths=paths, environ=runtime_env)
    except (ConfigError, OSError) as exc:
        raise Performance14Error(
            _sanitize_config_load_error(
                exc, api_key=runtime_env.get("OFFLINE_RAG_LLM_API_KEY")
            )
        ) from exc


def sanitize_runtime_settings_for_context(settings: AppSettings) -> AppSettings:
    """Return a copy safe for persistence: generation.api_key cleared."""
    return settings.model_copy(
        update={
            "generation": settings.generation.model_copy(update={"api_key": None})
        }
    )


def _redact_secrets(text: str, *, api_key: str | None) -> str:
    """Ensure API-key material never appears in preflight reasons/errors."""
    if api_key and api_key in text:
        return text.replace(api_key, "<redacted>")
    return text


def assert_runtime_generation_matches_freeze(
    settings: AppSettings,
    *,
    frozen_generation_semantic_payload: Mapping[str, object],
) -> str:
    """Fail closed unless effective generation runtime matches the Level-C pin."""
    gen = settings.generation
    sec = settings.security

    if not gen.enabled:
        raise Performance14Error("generation.enabled must be true for Level-C")
    if gen.provider != GENERATION_PROVIDER_LEVEL_C:
        raise Performance14Error(
            f"generation.provider must be {GENERATION_PROVIDER_LEVEL_C!r}"
        )
    if gen.model != GENERATION_MODEL_LEVEL_C:
        raise Performance14Error(
            f"generation.model must be {GENERATION_MODEL_LEVEL_C!r}"
        )
    if list(gen.approved_models) != [GENERATION_MODEL_LEVEL_C]:
        raise Performance14Error(
            "generation.approved_models must be exactly "
            f"[{GENERATION_MODEL_LEVEL_C!r}]"
        )
    if int(gen.timeout_seconds) != EXPECTED_TIMEOUT_SECONDS_LEVEL_C:
        raise Performance14Error(
            "generation.timeout_seconds must equal "
            f"{EXPECTED_TIMEOUT_SECONDS_LEVEL_C} (got {gen.timeout_seconds})"
        )
    if float(gen.temperature) != GENERATION_TEMPERATURE_LEVEL_C:
        raise Performance14Error("generation.temperature must be 0.0")
    if int(gen.max_output_tokens) != GENERATION_MAX_OUTPUT_TOKENS_LEVEL_C:
        raise Performance14Error(
            f"generation.max_output_tokens must be "
            f"{GENERATION_MAX_OUTPUT_TOKENS_LEVEL_C}"
        )
    if gen.prompt.strategy != GENERATION_PROMPT_STRATEGY_LEVEL_C:
        raise Performance14Error(
            f"generation.prompt.strategy must be "
            f"{GENERATION_PROMPT_STRATEGY_LEVEL_C!r}"
        )
    if gen.prompt.contract_version != GENERATION_PROMPT_CONTRACT_LEVEL_C:
        raise Performance14Error(
            f"generation.prompt.contract_version must be "
            f"{GENERATION_PROMPT_CONTRACT_LEVEL_C!r}"
        )
    if not sec.reject_unapproved_generation_endpoint:
        raise Performance14Error(
            "security.reject_unapproved_generation_endpoint must be true"
        )
    if not sec.reject_unapproved_generation_model:
        raise Performance14Error(
            "security.reject_unapproved_generation_model must be true"
        )

    try:
        selected = normalize_endpoint(gen.base_url)
        expected = normalize_endpoint(EXPECTED_GENERATION_ENDPOINT_LEVEL_C)
    except OpenAICompatibleGeneratorError as exc:
        raise Performance14Error(
            f"generation endpoint normalization failed: {exc}"
        ) from exc
    if selected != expected:
        raise Performance14Error(
            "generation.base_url must normalize to the frozen expected endpoint"
        )
    if not endpoint_authorized(gen.base_url, list(gen.approved_endpoints)):
        raise Performance14Error(
            "selected generation endpoint is not authorized by "
            "generation.approved_endpoints"
        )

    gencfg = build_generation_config_hash(settings)
    if gencfg != LOCKED_GENCFG_LEVEL_C:
        raise Performance14Error(
            "runtime generation_config_hash diverges from locked Level-C gencfg_"
        )
    runtime_payload = build_generation_semantic_payload(settings)
    if runtime_payload != dict(frozen_generation_semantic_payload):
        raise Performance14Error(
            "runtime generation_semantic_payload diverges from frozen Level-C payload"
        )
    return gencfg


def assert_runtime_context_matches_freeze(
    settings: AppSettings,
    *,
    frozen_context_semantic_payload: Mapping[str, object],
) -> str:
    counter = make_token_counter(settings)
    ctxcfg = build_context_config_hash(settings, token_counter=counter)
    if ctxcfg != LOCKED_CTXCFG_LEVEL_C:
        raise Performance14Error(
            "runtime context_config_hash diverges from locked Level-C ctxcfg_"
        )
    runtime_payload = build_context_semantic_payload(
        settings, token_counter=counter
    )
    if runtime_payload != dict(frozen_context_semantic_payload):
        raise Performance14Error(
            "runtime context_semantic_payload diverges from frozen Level-C payload"
        )
    return ctxcfg


def assert_recovery_disabled(settings: AppSettings) -> None:
    if settings.retrieval_recovery.enabled:
        raise Performance14Error(
            "retrieval_recovery.enabled must be false for Level-C"
        )


def assert_embedding_artifacts_ready(settings: AppSettings) -> Path:
    model_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    status = validate_embedding_artifacts(model_dir)
    if status.readiness != EmbeddingReadiness.READY:
        raise Performance14Error(
            f"embedding model artifacts not ready at {model_dir}: {status.reason}"
        )
    return status.path


def assert_frozen_suite_protocol_and_identities(repo_root: Path) -> tuple[str, str]:
    """Load/validate frozen artifact and prove locked scientific identities."""
    frozen = load_frozen_suite_artifact_level_c(repo_root=repo_root)
    plan = build_suite_plan_level_c(repo_root=repo_root)

    if frozen.execution_authorized:
        raise Performance14Error(
            "frozen Level-C artifact must keep execution_authorized=false"
        )
    if frozen.authoritative_results_authorized:
        raise Performance14Error(
            "frozen Level-C artifact must keep "
            "authoritative_results_authorized=false"
        )
    if frozen.suite_identity_hash != LOCKED_PERFSUITE_LEVEL_C:
        raise Performance14Error(
            "frozen suite_identity_hash diverges from locked Level-C perfsuite_"
        )
    if frozen.effective_config_id != LOCKED_PERFCFG_LEVEL_C:
        raise Performance14Error(
            "frozen effective_config_id diverges from locked Level-C perfcfg_"
        )
    recomputed_suite = assert_suite_identity(plan.suite)
    if recomputed_suite != LOCKED_PERFSUITE_LEVEL_C:
        raise Performance14Error(
            "recomputed suite identity diverges from locked Level-C perfsuite_"
        )
    recomputed_cfg = effective_config_id_level_c(repo_root=repo_root)
    if recomputed_cfg != LOCKED_PERFCFG_LEVEL_C:
        raise Performance14Error(
            "recomputed scientific config diverges from locked Level-C perfcfg_"
        )
    if list(frozen.query_ids) != list(QUERY_IDS_LEVEL_C):
        raise Performance14Error("frozen Level-C query membership drifted")
    if list(frozen.case_ids) != case_ids_level_c():
        raise Performance14Error("frozen Level-C case membership drifted")
    if frozen.variants != [VARIANT_HYBRID_RERANK_CONTEXT_GENERATION]:
        raise Performance14Error("frozen Level-C variant membership drifted")
    if frozen.warmup_count != WARMUP_COUNT_LEVEL_C:
        raise Performance14Error("frozen Level-C warmup_count drifted")
    if frozen.measured_repetitions != MEASURED_REPETITIONS_LEVEL_C:
        raise Performance14Error("frozen Level-C measured_repetitions drifted")
    if frozen.cold_warm != COLD_WARM_LEVEL_C:
        raise Performance14Error("frozen Level-C cold_warm drifted")
    if frozen.execution_order_contract != EXECUTION_ORDER_CONTRACT_LEVEL_C:
        raise Performance14Error("frozen Level-C execution_order_contract drifted")
    if frozen.generation_streaming:
        raise Performance14Error(
            "frozen Level-C generation_streaming must remain false"
        )
    if frozen.generation_config_hash != LOCKED_GENCFG_LEVEL_C:
        raise Performance14Error("frozen Level-C gencfg_ drifted")
    if frozen.context_config_hash != LOCKED_CTXCFG_LEVEL_C:
        raise Performance14Error("frozen Level-C ctxcfg_ drifted")

    assert_case_membership(plan)
    assert_protocol_counts(
        level="C",
        warmup_count=plan.warmup_count,
        measured_repetitions=plan.measured_repetitions,
    )
    assert_paired_comparison_invariant(plan)
    assert_treatment_only_config_delta(plan)
    return recomputed_suite, recomputed_cfg


def default_provider_probe(settings: AppSettings) -> GeneratorProbeResult:
    """Exactly one OpenAI-compatible ``/v1/models`` probe; never chat completions."""
    generator = OpenAICompatibleGenerator(settings)
    try:
        return generator.probe()
    finally:
        generator.close()


@dataclass(frozen=True, slots=True)
class LevelCPreflightContext:
    """Observational Level-C readiness context (does not authorize execution)."""

    repo_root: Path
    executing_sha: str
    suite_id: str
    scientific_config_id: str
    generation_config_id: str
    context_config_id: str
    freeze_authority: str
    instrumentation_authority: str
    machine_profile: PerformanceMachineProfileV1
    machine_profile_id: str
    results_parent: Path
    runtime_settings: AppSettings
    api_key_configured: bool
    provider_probe_performed: bool
    provider_probe_ok: bool | None
    execution_ready: bool
    preflight_record: PerformancePreflightRecordV1


def run_level_c_execution_preflight(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
    provider_probe: ProviderProbeMode = "skip",
    provider_probe_fn: ProviderProbeFn | None = None,
) -> LevelCPreflightContext:
    """Fail-closed Level-C execution-readiness preflight.

    ``execution_ready`` is observational only and never means execution is
    authorized. With ``provider_probe="skip"``, ``execution_ready`` is always
    ``False`` even when all local checks pass.

    Returned ``runtime_settings`` is sanitized (``generation.api_key is None``).
    """
    if provider_probe not in {"skip", "require"}:
        raise Performance14Error(
            f"provider_probe must be 'skip' or 'require'; got {provider_probe!r}"
        )

    acc = PreflightAccumulator()
    secret_api_key: str | None = None
    try:
        root = acc.run_check("repository_root", lambda: resolve_repo_root(repo_root))
        acc.repo_root = root
        acc.add("repository_root", "passed")

        executing_sha = acc.run_check(
            "executing_sha", lambda: resolve_executing_sha(root)
        )
        acc.executing_sha = executing_sha
        acc.add("executing_sha", "passed", executing_sha)

        acc.run_check(
            "working_tree_clean",
            lambda: assert_working_tree_clean_for_level_c(root),
        )
        acc.working_tree_state = "clean"
        acc.add("working_tree_clean", "passed", "clean")

        acc.run_check(
            "freeze_authority",
            lambda: assert_freeze_authority_reachable(root),
        )
        acc.add("freeze_authority", "passed", FREEZE_AUTHORITY_LEVEL_C)

        def _assert_instrumentation_authority() -> None:
            probe = subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    INSTRUMENTATION_AUTHORITY_LEVEL_C,
                    "HEAD",
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            if probe.returncode != 0:
                raise Performance14Error(
                    "accepted Level-C instrumentation authority "
                    f"{INSTRUMENTATION_AUTHORITY_LEVEL_C} is not an ancestor of HEAD"
                )

        acc.run_check(
            "instrumentation_authority",
            _assert_instrumentation_authority,
        )
        acc.add(
            "instrumentation_authority",
            "passed",
            INSTRUMENTATION_AUTHORITY_LEVEL_C,
        )

        suite_id, scientific_config_id = acc.run_check(
            "frozen_suite_identities",
            lambda: assert_frozen_suite_protocol_and_identities(root),
        )
        acc.suite_id = suite_id
        acc.add("frozen_suite_identities", "passed", suite_id)
        acc.add("scientific_config_id", "passed", scientific_config_id)

        gold_dir = root / GOLD_RELATIVE_PATH_14C
        acc.run_check(
            "gold_semantic_identity",
            lambda: assert_gold_semantic_identity_14c(gold_dir),
        )
        acc.add("gold_semantic_identity", "passed", GOLD_DATASET_ID_14C)

        frozen = load_frozen_suite_artifact_level_c(repo_root=root)

        runtime_env = acc.run_check(
            "runtime_environment",
            lambda: build_level_c_runtime_environment(
                root, environ=environ, dotenv_path=dotenv_path
            ),
        )
        acc.add("runtime_environment", "passed", "copied_env+dotenv")

        # Secret-bearing settings: local only; never returned on the context.
        secret_runtime_settings = acc.run_check(
            "runtime_settings",
            lambda: load_level_c_runtime_settings(
                root, runtime_env=runtime_env
            ),
        )
        secret_api_key = secret_runtime_settings.generation.api_key
        api_key_configured = bool(secret_api_key)
        acc.add("runtime_settings", "passed", "base.yaml+dotenv_copy")

        generation_config_id = acc.run_check(
            "generation_runtime_pin",
            lambda: assert_runtime_generation_matches_freeze(
                secret_runtime_settings,
                frozen_generation_semantic_payload=frozen.generation_semantic_payload,
            ),
        )
        acc.add("generation_runtime_pin", "passed", generation_config_id)

        context_config_id = acc.run_check(
            "context_runtime_pin",
            lambda: assert_runtime_context_matches_freeze(
                secret_runtime_settings,
                frozen_context_semantic_payload=frozen.context_semantic_payload,
            ),
        )
        acc.add("context_runtime_pin", "passed", context_config_id)

        acc.run_check(
            "recovery_disabled",
            lambda: assert_recovery_disabled(secret_runtime_settings),
        )
        acc.add("recovery_disabled", "passed", "false")

        if frozen.generation_streaming:
            raise Performance14Error("Level-C freeze forbids streaming generation")
        acc.add(
            "generation_streaming_invariant",
            "passed",
            "false/non-streaming-adapter",
        )

        # Substrate checks must honor the same path overrides as execution.
        hybrid_settings = acc.run_check(
            "hybrid_settings",
            lambda: load_level_c_hybrid_settings(root, runtime_env=runtime_env),
        )
        rerank_settings = acc.run_check(
            "hybrid_rerank_settings",
            lambda: load_level_c_hybrid_rerank_settings(
                root, runtime_env=runtime_env
            ),
        )
        acc.add("hybrid_settings", "passed", "hybrid_rrf+runtime_env")
        acc.add("hybrid_rerank_settings", "passed", "hybrid_rerank+runtime_env")

        acc.run_check(
            "index_and_config_pins",
            lambda: assert_index_and_config_pins(
                hybrid_settings=hybrid_settings,
                rerank_settings=rerank_settings,
            ),
        )
        acc.add("index_and_config_pins", "passed")

        emb_path = acc.run_check(
            "embedding_artifacts",
            lambda: assert_embedding_artifacts_ready(secret_runtime_settings),
        )
        acc.add("embedding_artifacts", "passed", str(emb_path))

        results_parent = reserved_results_root(root)

        def _prepare_output() -> Path:
            try:
                results_parent.mkdir(parents=True, exist_ok=True)
                probe_path = (
                    results_parent
                    / f".perf14_level_c_write_probe_{executing_sha[:8]}"
                )
                probe_path.write_text("ok", encoding="utf-8")
                probe_path.unlink(missing_ok=True)
            except OSError as exc:
                raise Performance14Error(
                    f"output destination not writable: {results_parent}: {exc}"
                ) from exc
            return results_parent

        parent = acc.run_check("output_writable", _prepare_output)
        acc.add("output_writable", "passed", str(parent))

        usage = shutil.disk_usage(parent)
        if usage.free < _MIN_DISK_FREE_BYTES:
            raise Performance14Error(
                f"insufficient disk capacity under {parent}: free={usage.free}"
            )
        acc.disk_capacity_sufficient = True
        acc.disk_free_bytes = int(usage.free)
        acc.add("disk_capacity", "passed", f"free_bytes={usage.free}")

        machine_profile, machine_profile_id = acc.run_check(
            "machine_profile",
            lambda: capture_machine_profile_with_id(
                offline_rag_commit_sha=executing_sha
            ),
        )
        acc.machine_profile = machine_profile
        acc.machine_profile_id = machine_profile_id
        acc.add("machine_profile", "passed", machine_profile_id)

        ram_av, _rss = observe_ram_rss_bytes()
        vram_av, _, _, _ = observe_vram()
        acc.telemetry_ram = ram_av
        acc.telemetry_vram = vram_av
        acc.add("telemetry_ram", "passed", ram_av)
        acc.add("telemetry_vram", "passed", vram_av)

        provider_probe_performed = False
        provider_probe_ok: bool | None = None
        if provider_probe == "skip":
            acc.add(
                "provider_probe",
                "not_applicable",
                "provider_probe=skip; not performed",
            )
            execution_ready = False
        else:
            probe_fn = provider_probe_fn or default_provider_probe

            def _require_provider_probe() -> GeneratorProbeResult:
                try:
                    result = probe_fn(secret_runtime_settings)
                except Performance14Error as exc:
                    raise Performance14Error(
                        _redact_secrets(str(exc), api_key=secret_api_key)
                    ) from exc
                except Exception as exc:
                    raise Performance14Error(
                        _redact_secrets(
                            f"provider readiness probe raised: "
                            f"{type(exc).__name__}: {exc}",
                            api_key=secret_api_key,
                        )
                    ) from exc
                if not result.ok:
                    raise Performance14Error(
                        _redact_secrets(
                            f"provider readiness probe failed: {result.reason}",
                            api_key=secret_api_key,
                        )
                    )
                return result

            result = acc.run_check("provider_probe", _require_provider_probe)
            provider_probe_performed = True
            provider_probe_ok = True
            acc.add("provider_probe", "passed", result.reason or "ok")
            execution_ready = True

        sanitized_settings = sanitize_runtime_settings_for_context(
            secret_runtime_settings
        )
        if sanitized_settings.generation.api_key is not None:
            raise Performance14Error(
                "sanitized runtime_settings still contains generation.api_key"
            )

        record = acc.to_record(status="passed")
        _assert_record_secret_hygiene(record, api_key=secret_api_key)

        ctx = LevelCPreflightContext(
            repo_root=root,
            executing_sha=executing_sha,
            suite_id=suite_id,
            scientific_config_id=scientific_config_id,
            generation_config_id=generation_config_id,
            context_config_id=context_config_id,
            freeze_authority=FREEZE_AUTHORITY_LEVEL_C,
            instrumentation_authority=INSTRUMENTATION_AUTHORITY_LEVEL_C,
            machine_profile=machine_profile,
            machine_profile_id=machine_profile_id,
            results_parent=parent,
            runtime_settings=sanitized_settings,
            api_key_configured=api_key_configured,
            provider_probe_performed=provider_probe_performed,
            provider_probe_ok=provider_probe_ok,
            execution_ready=execution_ready,
            preflight_record=record,
        )
        _assert_context_secret_hygiene(ctx, api_key=secret_api_key)
        return ctx
    except Performance14Error as exc:
        message = _redact_secrets(str(exc), api_key=secret_api_key)
        if acc.error is not None:
            acc.error = _redact_secrets(acc.error, api_key=secret_api_key)
        if acc.failing_check is None:
            acc.fail("preflight", message)
        record = acc.to_record(status="failed")
        _assert_record_secret_hygiene(record, api_key=secret_api_key)
        redacted = Performance14Error(message)
        redacted.preflight_record = record  # type: ignore[attr-defined]
        redacted.preflight_partial = acc  # type: ignore[attr-defined]
        raise redacted from exc


def _assert_record_secret_hygiene(
    record: PerformancePreflightRecordV1,
    *,
    api_key: str | None,
) -> None:
    if not api_key:
        return
    encoded = str(record.model_dump(mode="json"))
    if api_key in encoded:
        raise Performance14Error(
            "preflight record leaked generation API key material"
        )


def _assert_context_secret_hygiene(
    ctx: LevelCPreflightContext,
    *,
    api_key: str | None,
) -> None:
    if ctx.runtime_settings.generation.api_key is not None:
        raise Performance14Error(
            "returned LevelCPreflightContext retains generation.api_key"
        )
    if not api_key:
        return
    # Serializable / printable evidence must not retain the raw secret.
    evidence = (
        str(ctx.runtime_settings.model_dump(mode="json")),
        str(ctx.preflight_record.model_dump(mode="json")),
        repr(ctx.runtime_settings),
        repr(ctx),
    )
    for blob in evidence:
        if api_key in blob:
            raise Performance14Error(
                "returned LevelCPreflightContext leaked generation API key material"
            )
