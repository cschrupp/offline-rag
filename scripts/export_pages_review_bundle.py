#!/usr/bin/env python3
"""Export a private Pages review bundle from a gold-authoring run.

Writes offline-rag-pages-review-bundle-v1 JSON for the static expert-review
app on branch pages/9f-expert-review. Does not mutate the Silver run.

Never commit the output (it contains private candidate text).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from offline_rag.cli import _resolve_settings
from offline_rag.config.loader import load_dotenv, load_settings
from offline_rag.gold_authoring.persist import load_authoring_run
from offline_rag.gold_authoring.review_models import ReviewError
from offline_rag.gold_authoring.review_view import build_case_detail_payload

BUNDLE_SCHEMA = "offline-rag-pages-review-bundle-v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a private Pages expert-review bundle from a silver run."
    )
    parser.add_argument(
        "--run",
        required=True,
        type=Path,
        help="Path to gold-authoring run JSON",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="YAML config path (repeatable; later overrides earlier)",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output bundle path (keep outside git; contains private text)",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    yaml_paths = [Path(p) for p in args.config] or [Path("config/base.yaml")]
    settings = _resolve_settings(load_settings(yaml_paths=yaml_paths))

    run_path = args.run
    if not run_path.exists():
        print(f"export_pages_review_bundle: run not found: {run_path}", file=sys.stderr)
        return 2

    try:
        run = load_authoring_run(run_path)
    except Exception as exc:  # noqa: BLE001
        print(f"export_pages_review_bundle: invalid run: {exc}", file=sys.stderr)
        return 2

    cases = []
    for ordinal, case in enumerate(run.cases, start=1):
        try:
            detail = build_case_detail_payload(settings, run, case)
        except ReviewError as exc:
            print(
                f"export_pages_review_bundle: case {case.draft_case_id}: {exc}",
                file=sys.stderr,
            )
            return 2
        detail = dict(detail)
        detail["ordinal"] = ordinal
        # Strip live-server capability flags; the static app recomputes them.
        for key in (
            "can_accept",
            "can_approve_edited",
            "can_reject",
            "can_reopen",
            "judged_count",
            "human_positive_count",
            "review_complete",
            "status",
            "effective_query",
            "effective_category",
            "effective_tags",
            "query_edited",
            "model_prelabels_for_proposed_query",
        ):
            detail.pop(key, None)
        # Keep proposed_* and candidates with null human_relevance for a clean bundle.
        for cand in detail.get("candidates") or []:
            cand["human_relevance"] = None
        cases.append(detail)

    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "authoring_run_id": run.authoring_run_id,
        "chunk_set_id": run.chunk_set_id,
        "corpus_name": run.corpus_name,
        "cases": cases,
    }

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"  schema: {BUNDLE_SCHEMA}")
    print(f"  authoring_run_id: {run.authoring_run_id}")
    print(f"  cases: {len(cases)}")
    print(f"  candidates: {sum(len(c.get('candidates') or []) for c in cases)}")
    print("Do not commit this file (private candidate text).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
