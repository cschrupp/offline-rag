"""Artifact persistence helpers for Slice 14B dry-run runs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkRunManifestV1,
    PerformancePreflightRecordV1,
    PerformanceRunAggregateV1,
)


def _write_new_text(path: Path, text: str) -> None:
    """Create ``path`` exclusively; fail closed if it already exists."""
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise Performance14Error(
            f"refusing to overwrite existing run artifact: {path}"
        ) from exc


def write_run_artifacts(
    output_dir: Path,
    *,
    manifest: PerformanceBenchmarkRunManifestV1,
    aggregate: PerformanceRunAggregateV1,
    cases: Sequence[PerformanceBenchmarkCaseV1],
    report_markdown: str,
    preflight: PerformancePreflightRecordV1 | None = None,
) -> None:
    """Write immutable run_manifest / aggregate / cases / report / preflight."""
    cases_dir = output_dir / "cases"
    try:
        cases_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise Performance14Error(
            f"refusing to reuse existing cases directory: {cases_dir}"
        ) from exc

    _write_new_text(
        output_dir / "run_manifest.json",
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    _write_new_text(
        output_dir / "aggregate.json",
        json.dumps(aggregate.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    if preflight is not None:
        _write_new_text(
            output_dir / "preflight.json",
            json.dumps(preflight.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
        )
    for case in cases:
        _write_new_text(
            cases_dir / f"{case.case_id}.json",
            json.dumps(case.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        )
    _write_new_text(output_dir / "report.md", report_markdown)
