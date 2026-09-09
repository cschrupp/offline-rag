#!/usr/bin/env python3
"""Provision local Docling artifacts for offline PDF parsing.

Network access is allowed only during this explicit provisioning step.
Parsing runtime never downloads artifacts.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/docling"),
        help="Local Docling artifacts directory",
    )
    args = parser.parse_args()

    import docling
    from docling.utils.model_downloader import download_models

    from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    print(f"Provisioning Docling artifacts into {output}")
    download_models(output_dir=output, progress=True, force=False)
    write_provisioning_manifest(
        output,
        docling_version=getattr(docling, "__version__", "unknown"),
    )
    print("Provisioning complete.")
    print(f"Manifest: {output / 'offline-rag-artifacts.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
