"""Static global startup readiness checks (D09 / D16) — no network probes."""

from __future__ import annotations

from offline_rag.chunking.tokenize import validate_tiktoken_artifacts
from offline_rag.config.models import AppSettings
from offline_rag.generation.status import validate_generation_static_config
from offline_rag.ingestion.docling_artifacts import validate_docling_artifacts


def validate_global_startup_requirements(settings: AppSettings) -> None:
    """Validate globally required local assets and generator config.

    Fail closed on missing Docling/tokenizer artifacts or unapproved
    generation endpoint/model. Does not download assets and does not probe
    generator connectivity.
    """
    docling = validate_docling_artifacts(settings.paths.docling_artifacts)
    if not docling.ready:
        raise RuntimeError(f"Docling artifacts not ready: {docling.reason}")

    tok_ok, tok_reason = validate_tiktoken_artifacts(
        settings.paths.tokenizer_artifacts,
        encoding=settings.chunking.tokenizer.encoding,
    )
    if not tok_ok:
        raise RuntimeError(f"Tokenizer artifacts not ready: {tok_reason}")

    validate_generation_static_config(settings)
