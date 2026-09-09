#!/usr/bin/env python3
"""Maintenance-only generator for the born-digital PDF fixture.

Not invoked by pytest. Optional developer dependency: none (stdlib PDF writer).
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_content(lines: list[str], *, y_start: int = 750) -> str:
    commands = ["BT", "/F1 11 Tf", "14 TL", f"72 {y_start} Td"]
    first = True
    for line in lines:
        if not first:
            commands.append("T*")
        commands.append(f"({_escape(line)}) Tj")
        first = False
    commands.append("ET")
    return "\n".join(commands)


def build_pdf() -> bytes:
    pages = [
        [
            "OfflineRAG PDF Parsing Reference",
            "OFFLINERAG_FIXTURE_PAGE_1",
            "1. System Overview",
            "This document is a deterministic fixture used to validate OfflineRAG PDF ingestion.",
            "It targets born-digital layout extraction with OCR disabled.",
            "1.1 Operating Conditions",
            "The reference system operates at a nominal pressure of 10,000 psi",
            "and a nominal temperature of 150 C.",
            "Operating limits:",
            "- Maximum pressure: 15,000 psi",
            "- Maximum temperature: 175 C",
            "- Minimum flow rate: 2.5 L/min",
        ],
        [
            "OFFLINERAG_FIXTURE_PAGE_2",
            "2. Equipment Limits",
            "Tool | Maximum Pressure | Maximum Temperature",
            "Alpha | 10,000 psi | 150 C",
            "Beta | 15,000 psi | 175 C",
            "Gamma | 12,500 psi | 160 C",
            "The Beta tool supports the highest pressure rating of 15,000 psi.",
        ],
        [
            "OFFLINERAG_FIXTURE_PAGE_3",
            "3. Operational Notes",
            "3.1 Shutdown Procedure",
            "1. Isolate flow",
            "2. Depressurize the tool",
            "3. Confirm gauges read zero",
            "Follow the shutdown procedure before maintenance.",
        ],
    ]

    objects: list[bytes] = []
    # 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2: Pages (filled later)
    objects.append(b"")  # placeholder
    # 3: Font
    objects.append(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    page_objs: list[int] = []
    next_id = 4
    for lines in pages:
        content = _page_content(lines).encode("latin-1", errors="replace")
        content_id = next_id
        page_id = next_id + 1
        next_id += 2
        objects.append(
            f"{content_id} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode()
            + content
            + b"\nendstream\nendobj\n"
        )
        objects.append(
            (
                f"{page_id} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>\n"
                f"endobj\n"
            ).encode()
        )
        page_objs.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_objs)
    objects[1] = (
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_objs)} >>\nendobj\n".encode()
    )

    # Assemble with xref
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode()
    )
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/ingestion/pdf/born_digital_reference.pdf"),
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing fixture")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        print(f"Refusing to overwrite {args.output} without --force")
        return 1
    data = build_pdf()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"Wrote {args.output} ({len(data)} bytes)")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
