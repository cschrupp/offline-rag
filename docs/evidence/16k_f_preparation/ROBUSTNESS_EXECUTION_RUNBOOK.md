# 16K-F Replacement Corpus Robustness Runbook

**Status:** `PREPARED — REAL-CORPUS EXECUTION NOT AUTHORIZED`

This runbook complements the cold/warm harness for the rejection and recovery
cases in `CORPUS_BASELINE_AMENDMENT_001.md`. It does not authorize execution.
Use it only under a later explicit 16K-F execution authority.

## Preconditions

1. Use a dedicated Seneca API process and isolated `OFFLINE_RAG_DATA_DIR`.
   Never use a personal or beta workspace.
2. Verify `/health/ready` returns HTTP 200 and record the active capabilities.
3. Verify the private replacement manifest and query-deck bytes against both
   the accepted execution authority and these prepared pins:

   ```text
   manifest canonical SHA-256:
   4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b

   query-deck file-byte SHA-256:
   f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a
   ```

   The cold/warm runner also requires the authority-provided values:

   ```bash
   .venv/bin/python -m scripts.diag_16k_f.execution_harness run-full-pair \
     --approved-manifest-sha256 "$APPROVED_MANIFEST_SHA256" \
     --approved-query-deck-file-sha256 "$APPROVED_QUERY_DECK_FILE_SHA256" \
     ...
   ```

   Missing or mismatched pins fail before the runner makes an API request.
   Cell evidence records both verified artifact identities.
4. Keep all raw source names, paths, query text, answers, and operation payloads
   in the private execution directory. Committed/surfaced summaries contain
   hashes and bounded status fields only.

## Case sequence

Use the exact scenario IDs in the private manifest's
`robustness_matrix.scenarios`; do not reconstruct case membership from
filenames. The replacement manifest retains all 52 paths: 3 oversized PDFs,
3 OCR-required PDFs, and 8 additional paths that duplicate an eligible byte
identity. The 38-source cold/warm population remains separate.

For every rejection case:

1. Record workspace state immediately before the mutation.
2. Submit the case through `POST /v1/workspaces/{workspace_id}/sources` with the
   current `If-Match` revision and a fresh `Idempotency-Key`.
3. Capture either the immediate 4xx response or the accepted 202 operation and
   poll it to a terminal state. Re-read terminal operation state using a fresh
   client connection.
4. Read `/health/ready` and workspace/source state again. The published
   revision, snapshot, source count, and canonical source-identity digest must
   match the pre-mutation values.
5. For mixed-batch cases, send one eligible new source together with the
   invalid input in the same multipart request. Do not split the request to
   make it pass.
6. After each mixed rejection, submit the valid source by itself using the
   current revision and a new idempotency key. Require a succeeded operation,
   exactly one revision increase, one added active source, and readiness 200.

Execute the prepared scenarios in this order:

1. Each of the 3 oversized paths individually; expect admission rejection.
2. Each of the 3 OCR-required paths individually; expect the frozen OCR-disabled
   actionable failure.
3. Each of the 8 exact duplicate paths against a workspace where the matching
   eligible identity is active; require duplicate rejection/reporting without
   a second active source.
4. Mixed eligible + oversized, mixed eligible + OCR-required, and mixed
   eligible + already-active duplicate. For each, prove atomic preservation
   and then successful same-process retry of the valid source alone.
5. Query the final published corpus using the private grounded-query deck; use
   the existing query acceptance checks.

Run the three mixed cases in a dedicated workspace seeded with one small
eligible source. Do not consume or alter the full-corpus cold/warm workspace.
Use separate workspaces for individual cases where a prior successful retry
would affect duplicate membership or publication state.

## Structured evidence

Write one private JSON record per expected-rejection case using this schema:

```json
{
  "schema": "16k-f-robustness-case-evidence-v1",
  "case_id": "manifest scenario ID plus private case ordinal",
  "expected_failure_category": "oversized | ocr_required | duplicate",
  "input_source_sha256s": ["lowercase SHA-256 values only"],
  "before": {
    "revision": 1,
    "snapshot_id": "snapshot ID or empty string",
    "source_count": 1,
    "source_identity_sha256": "64 lowercase hex characters"
  },
  "rejection": {
    "http_status": 413,
    "operation_status": null,
    "safe_error_code": "document_invalid",
    "reason": "source_file_too_large"
  },
  "after": {
    "revision": 1,
    "snapshot_id": "same snapshot ID or empty string",
    "source_count": 1,
    "source_identity_sha256": "same digest"
  },
  "readiness_http_status": 200,
  "retry_required": false,
  "retry": null
}
```

For a 202 managed rejection, set `operation_status` to its terminal status and
record its sanitized public error code and reason. For each mixed rejection,
set `retry_required` to `true` and add `retry` with `status`, `revision`,
`snapshot_id`, `source_count`, `source_identity_sha256`, and
`readiness_http_status` from the subsequent valid source-add.

The source identity digest is SHA-256 over the UTF-8 bytes of sorted active
`document_id:content_hash` pairs joined by a single newline, with no trailing
newline. Empty workspaces use SHA-256 of the empty byte string. Keep the
individual identities private.

Validate each record and emit a sanitized summary:

```bash
.venv/bin/python -m scripts.diag_16k_f.execution_harness \
  validate-robustness-evidence \
  --input "$PRIVATE_EVIDENCE/case.json" \
  --output "$PRIVATE_EVIDENCE/case-summary.json"
```

The validator fails if a rejection changes publication state, readiness is
not 200, the public error is not in the expected category, or a required retry
does not succeed with exactly one revision/source increase. Review the
sanitized summaries together with API logs before declaring a case passed.

## Markdown coverage and measurement scope

The frozen 52-path replacement population contains 37 PDFs, one TXT, and zero
Markdown files. The focused preparation suite includes a synthetic parser-only
Markdown smoke; it does not cover a managed `SOURCE_ADD` or add a source to the
replacement manifest, cold/warm source count, or scientific workload. A
separate API smoke attempt stalled during `TestClient` lifespan startup and
was stopped after 30 seconds. Beta reporting must continue to say that
real-corpus Markdown ingestion was not demonstrated by the replacement
corpus.

No expected-rejection operation is included in cold/warm totals. The
38-source replacement measurements remain explicitly non-comparable to the
historical 39-primary threshold population.
