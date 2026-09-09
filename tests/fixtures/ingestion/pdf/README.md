# Born-digital PDF fixture

## File

`born_digital_reference.pdf`

## Purpose

Deterministic synthetic PDF for Slice 1 Docling integration tests.

## Profile

- Pages: 3
- OCR policy: disabled
- Parser profile: born-digital Docling layout path
- No images, encryption, or external fonts

## Expected headings

- 1. System Overview
- 1.1 Operating Conditions
- 2. Equipment Limits
- 3. Operational Notes
- 3.1 Shutdown Procedure

## Expected table content

Rows for tools: Alpha, Beta, Gamma  
Notable value: `15,000 psi`

## Sentinels

| Page | Sentinel |
| --- | --- |
| 1 | `OFFLINERAG_FIXTURE_PAGE_1` |
| 2 | `OFFLINERAG_FIXTURE_PAGE_2` |
| 3 | `OFFLINERAG_FIXTURE_PAGE_3` |

## SHA-256

```text
d81dc0d89641eb0cad9176051865e1ef13e8ee77f926f3f157e935eac08cfcbf
```

## Regeneration

```bash
uv run python scripts/generate_pdf_fixture.py --force
```

Update this checksum after intentional regeneration. Pytest uses the committed binary only and does not run the generator.
