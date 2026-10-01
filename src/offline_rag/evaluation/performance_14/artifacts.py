"""Artifact persistence helpers for Slice 14B dry-run runs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from offline_rag.evaluation.performance_14.contracts import (
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceRunAggregateV1,
)


def write_run_artifacts(
    output_dir: Path,
    *,
    manifest: PerformanceBenchmarkRunManifestV1,
    aggregate: PerformanceRunAggregateV1,
    cases: Sequence[PerformanceBenchmarkCaseV1],
    report_markdown: str,
) -> None:
    """Write immutable run_manifest / aggregate / cases / report.md."""
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "aggregate.json").write_text(
        json.dumps(aggregate.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for case in cases:
        path = cases_dir / f"{case.case_id}.json"
        path.write_text(
            json.dumps(case.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (output_dir / "report.md").write_text(report_markdown, encoding="utf-8")
