"""CLI shell for OfflineRAG.

Slice 0 provides command hierarchy and placeholder behavior only. Ingestion,
retrieval, and evaluation execution are intentionally unimplemented.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from offline_rag.config import ConfigError, load_settings
from offline_rag.observability import configure_logging, log_event

NOT_IMPLEMENTED_EXIT = 2


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    return _repo_root() / "config" / "base.yaml"


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        action="append",
        default=None,
        help="YAML config path (repeatable; later files override earlier ones)",
    )


def _not_implemented(command: str) -> int:
    print(
        f"offline-rag {command}: not implemented in this slice "
        "(Slice 0 establishes contracts only).",
        file=sys.stderr,
    )
    return NOT_IMPLEMENTED_EXIT


def cmd_ingest(_args: argparse.Namespace) -> int:
    return _not_implemented("ingest")


def cmd_query(_args: argparse.Namespace) -> int:
    return _not_implemented("query")


def cmd_eval_run(_args: argparse.Namespace) -> int:
    return _not_implemented("eval run")


def cmd_eval_compare(_args: argparse.Namespace) -> int:
    return _not_implemented("eval compare")


def cmd_doctor(args: argparse.Namespace) -> int:
    """Slice-0-safe local checks only. No Ollama or model loading."""
    yaml_paths = args.config or [_default_config_path()]
    try:
        settings = load_settings(yaml_paths=yaml_paths)
    except ConfigError as exc:
        print(f"doctor: configuration failed: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(
        level=settings.logging.level,
        structured=settings.logging.structured,
    )
    log_event(logger, 20, "doctor started", event="doctor.start")

    errors: list[str] = []

    if settings.project.strict_offline:
        if settings.security.reject_unapproved_generation_endpoint and not settings.generation.approved_endpoints:
            errors.append("strict_offline requires generation.approved_endpoints when endpoint rejection is enabled")
        if settings.security.allow_network_tools:
            errors.append("strict_offline is incompatible with security.allow_network_tools=true")

    path_fields = [
        ("raw_data", settings.paths.raw_data),
        ("manifests", settings.paths.manifests),
        ("processed", settings.paths.processed),
        ("qdrant_storage", settings.paths.qdrant_storage),
        ("retrieval_models", settings.paths.retrieval_models),
        ("eval_results", settings.paths.eval_results),
    ]

    for name, path in path_fields:
        if not path.exists():
            errors.append(f"configured path does not exist: paths.{name}={path}")
            continue
        if name == "retrieval_models":
            if not path.is_dir():
                errors.append(f"retrieval_models must be a directory: {path}")
            continue
        if not path.is_dir():
            errors.append(f"path must be a directory: paths.{name}={path}")
            continue
        probe = path / ".offline_rag_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"path is not writable: paths.{name}={path} ({exc})")

    if errors:
        for error in errors:
            print(f"doctor: FAIL: {error}", file=sys.stderr)
            log_event(logger, 40, error, event="doctor.check_failed")
        return 1

    print("doctor: OK — configuration valid; local paths usable; no model checks performed.")
    log_event(logger, 20, "doctor completed successfully", event="doctor.ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offline-rag",
        description="OfflineRAG CLI (Slice 0 foundation shell)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest documents (not implemented in Slice 0)")
    _add_config_argument(ingest)
    ingest.set_defaults(func=cmd_ingest)

    query = subparsers.add_parser("query", help="Query the corpus (not implemented in Slice 0)")
    _add_config_argument(query)
    query.set_defaults(func=cmd_query)

    eval_parser = subparsers.add_parser("eval", help="Evaluation commands")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)

    eval_run = eval_sub.add_parser("run", help="Run evaluation (not implemented in Slice 0)")
    _add_config_argument(eval_run)
    eval_run.set_defaults(func=cmd_eval_run)

    eval_compare = eval_sub.add_parser("compare", help="Compare evaluations (not implemented in Slice 0)")
    _add_config_argument(eval_compare)
    eval_compare.set_defaults(func=cmd_eval_compare)

    doctor = subparsers.add_parser("doctor", help="Run Slice-0-safe local diagnostics")
    _add_config_argument(doctor)
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
