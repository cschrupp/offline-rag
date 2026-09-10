#!/usr/bin/env python3
"""Provision local tiktoken encoding artifacts for offline chunk budgeting."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/tokenizers/tiktoken"),
    )
    parser.add_argument("--encoding", default="cl100k_base")
    args = parser.parse_args()

    import tiktoken

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(output)
    print(f"Provisioning tiktoken encoding {args.encoding} into {output}")
    enc = tiktoken.get_encoding(args.encoding)
    probe = len(enc.encode("OfflineRAG tokenizer provisioning"))
    manifest = {
        "schema_version": 1,
        "provider": "tiktoken",
        "encoding": args.encoding,
        "tiktoken_version": getattr(tiktoken, "__version__", "unknown"),
        "probe_token_count": probe,
        "provisioned_at": datetime.now(tz=UTC).isoformat(),
    }
    (output / "offline-rag-tokenizer.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Provisioning complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
