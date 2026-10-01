"""Human-readable report.md presentation for Slice 14B (not acceptance authority)."""

from __future__ import annotations

from collections.abc import Sequence

from offline_rag.evaluation.performance_14.contracts import (
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceRunAggregateV1,
)


def render_report_markdown(
    *,
    run_id: str,
    manifest: PerformanceBenchmarkRunManifestV1,
    aggregate: PerformanceRunAggregateV1,
    cases: Sequence[PerformanceBenchmarkCaseV1],
    error: str | None = None,
) -> str:
    lines = [
        f"# Slice 14B performance dry-run report ({run_id})",
        "",
        "Evidence class: **DIAGNOSTIC ONLY / NON-AUTHORITATIVE**",
        "",
        "This report is presentation only. Raw observations are authoritative for",
        "the dry-run harness validation; aggregates are deterministic derivations.",
        "No SLOs, winners, or promotion decisions are produced.",
        "",
        f"- suite_id: `{manifest.suite_id}`",
        f"- run_identity_hash: `{manifest.run_identity_hash}`",
        f"- executing_sha: `{manifest.executing_sha}`",
        f"- machine_profile_id: `{manifest.machine_profile_id}`",
        f"- config_id: `{manifest.config_id}`",
        f"- corpus_id: `{manifest.corpus_id}`",
        f"- execution_mode: `{manifest.execution_mode}`",
        f"- run_status: `{aggregate.run_status}`",
        f"- benchmark_level: `{aggregate.benchmark_level}`",
        f"- case_count: `{len(cases)}`",
        f"- diagnostic_only: `{aggregate.diagnostic_only}`",
        f"- authoritative: `{aggregate.authoritative}`",
    ]
    if aggregate.overall is not None:
        overall = aggregate.overall
        lines.extend(
            [
                "",
                "## Overall measured accounting",
                "",
                f"- attempted_count: `{overall.attempted_count}`",
                f"- valid_count: `{overall.valid_count}`",
                f"- failure_count: `{overall.failure_count}`",
                (
                    f"- instrumentation_exclusion_count: "
                    f"`{overall.instrumentation_exclusion_count}`"
                ),
                f"- warmup_count: `{overall.warmup_count}`",
                f"- n: `{overall.n}`",
                f"- min: `{overall.min}`",
                f"- p50: `{overall.p50}`",
                f"- p95: `{overall.p95}`",
                f"- max: `{overall.max}`",
            ]
        )
    if aggregate.by_variant:
        lines.extend(["", "## By variant", ""])
        for item in aggregate.by_variant:
            lines.append(
                f"- `{item.variant}`: n={item.stats.n} "
                f"attempted={item.stats.attempted_count} "
                f"failures={item.stats.failure_count} "
                f"exclusions={item.stats.instrumentation_exclusion_count}"
            )
    if error:
        lines.extend(["", f"- error: `{error}`"])
    lines.append("")
    return "\n".join(lines)
