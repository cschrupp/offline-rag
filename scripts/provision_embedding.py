#!/usr/bin/env python3
"""Thin wrapper around offline-rag provision embedding.

Network access is allowed only during this explicit provisioning step.
Dense indexing/retrieval runtime never downloads embedding weights.
"""

from __future__ import annotations

import sys

from offline_rag.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return cli_main(["provision", "embedding", *args])


if __name__ == "__main__":
    raise SystemExit(main())
