# 16K-F Combined Corrective — Implementation Result

**Authority:** Human authorization, “16K-F Combined Corrective Implementation”
**Base:** `895870cb5ff12a7ffdf438759a3070dd224f4daf`
**Branch:** `prep/16k-f-corpus-acceptance`
**Scope:** OCR-required zero-block rejection, truthful warm-cache timing validation,
and GPU-residency backlog reconciliation.

## Implementation

- The ingestion pipeline rejects a parsed PDF when it carries an
  `OCR_REQUIRED` warning and has no parsed blocks. The check runs both for new
  parses and reused parsed artifacts. A safe `ocr_required` document reason is
  carried through the managed operation API and mapped to actionable UI copy.
- PDFs with parsed blocks remain eligible, including short text with the
  existing OCR warning and partially text-bearing PDFs. The 40-character
  warning heuristic, OCR configuration, product limits, and capacity policy
  are unchanged.
- The 16K-F operation validator permits omitted dense-generation and
  dense-materialization durations only when `embeddings_generated == 0` and
  `embeddings_reused > 0`. Missing values remain absent; no zero timings are
  synthesized. All other stage durations and existing metric checks remain
  required.
- The existing GPU-residency diagnostics are reconciled in `docs/BACKLOG.md` as
  `GPU-RESIDENCY-01`. They established a negative constrained/free-VRAM result
  and did not establish API-process model residency or the historical HTTP-500
  root cause. The backlog distinguishes live model weights, PyTorch allocator
  reserved cache, and external/device-owned memory, and records resident,
  idle-eviction, and worker-isolation options without selecting or implementing
  a lifecycle policy.

Changed files:

- `src/offline_rag/ingestion/pipeline.py`
- `src/offline_rag/app/ingest.py`
- `scripts/diag_16k_f/execution_harness.py`
- `ui/src/api/errors.ts`
- `tests/unit/test_ingestion_pipeline.py`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py`
- `tests/unit/test_slice16k_f_corpus_preparation.py`
- `ui/src/test/p4_human_uat_duplicate_message.test.ts`
- `docs/BACKLOG.md`
- `docs/evidence/16k_f_preparation/CORRECTIVE_IMPLEMENTATION_RESULT.md`

## Regression coverage

Focused tests cover a mixed valid/OCR-required rejection with unchanged corpus
state; a cached empty OCR-required artifact; accepted short and partial PDFs
that produce blocks; managed-workspace revision/snapshot/source preservation;
safe public error classification and UI copy; reuse-only missing dense timing;
missing required timings; and the requirement for positive reuse evidence.

## Validation

```yaml
focused_python_suite_before_final_added_negative_metric_case:
  command: uv run pytest -q tests/unit/test_ingestion_pipeline.py tests/unit/test_slice16k_f_corpus_preparation.py tests/unit/app/test_slice16k_b_ingestion_observability.py
  result: 66 passed
  note: complete run included the managed-workspace atomicity test

canonical_venv_unit_rerun:
  command: .venv/bin/python -m pytest -q tests/unit/test_ingestion_pipeline.py tests/unit/test_slice16k_f_corpus_preparation.py
  result: 39 passed

ui_copy_test:
  command: ui/node_modules/.bin/vitest run src/test/p4_human_uat_duplicate_message.test.ts
  result: 4 passed

ruff_check_changed_python:
  result: PASS with S110 ignored
  standard_check: one existing S110 in app/ingest.py:_run_stage

ruff_format_check:
  result: NOT CLEAN
  note: existing whole-file formatting drift; no broad reformat applied

git_diff_check:
  result: PASS

run_001_hash_inventory:
  result: IDENTICAL before and after corrective work
```

A later complete retry reached a `TestClient` startup stall and was stopped;
the same managed-workspace test had passed in the earlier complete run. The
canonical-venv unit rerun includes the final added telemetry negative case.
Real-corpus execution, scientific execution, and promotion were not performed.

## Evidence and remaining boundary

`artifacts/16k_f_execution/run_001/` remains local and unchanged. Its original
failed cold-cell record remains failed; the five successful query-retry results
remain separate supplementary evidence. This corrective does not qualify the
incomplete warm cell or complete the 16K-F campaign.

After independent review, resume first with OCR robustness and warm-cache
handling. Then continue the remaining authorized campaign cases, preserving the
original cold ingestion and query evidence. If the accepted immediate cold/warm
pair requirement cannot be met by a documented recovery consistent with the
accepted contract, run a fresh isolated pair under the existing campaign
authority. No new scientific execution is authorized by this implementation
record.
