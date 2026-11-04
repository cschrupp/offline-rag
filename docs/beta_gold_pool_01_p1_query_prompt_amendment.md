# BETA-GOLD-POOL-01 — Qualified query-prompt runtime amendment

**Parent contract:** accepted dual-backend P1 runtime subject
`fae82b2455cfdd0d1622065904a35895372740b6`

**Status:** implementation amendment under bounded Human authorization.
This amendment is limited to query-side execution of
`model-query-prompt-v1` for the existing qualified production profiles.

## Reason

Gold Lab's accepted `candidate-pooling-v1` contract includes a distinct
`dense-model-query-prompt-v1` arm. The qualified P1 runtime previously admitted
only `raw-query-v1`, making that arm fail before retrieval on both supported
profiles. The amendment aligns the runtime's supported query representations
with the existing pooling contract; it does not change the six-arm ensemble.

## Amended runtime contract

Both `cuda_fp16_v1` and `cpu_onnx_fp32_v1` may execute either:

- `raw-query-v1`, preserving its current bare-query behavior; or
- `model-query-prompt-v1`, using the provisioned model's non-empty registered
  SentenceTransformers prompt named `query`.

For the prompt contract, each adapter must validate the loaded model's prompt
registry and call SentenceTransformers with `prompt_name="query"`. It must not
manually substitute a raw query, concatenate an unregistered prompt, or fall
back to raw-query execution. Missing, empty, or invalid prompt metadata fails
closed with a bounded operational error.

The CPU ONNX adapter uses the same `SentenceTransformer.encode(...,
prompt_name="query")` contract through the shared ONNX runtime substrate. Its
qualification compares registered-prompt query vectors against the same pinned
model revision running the standard PyTorch FP32 SentenceTransformers adapter.
It reuses the accepted D2 query-vector cosine thresholds; no threshold is
relaxed for this amendment. CPU prompt execution is not qualified unless this
check passes. CUDA uses the existing registered prompt mechanism and receives
equivalent missing/invalid-prompt coverage.

## Preserved contracts

- The default production query contract remains `raw-query-v1`.
- Query prompt behavior is selected only by the explicit query-text setting or
  the Gold pooling arm's derived settings.
- Document embedding text, representation identities, cache identity,
  embedding/index identities, and existing published indexes are unchanged.
- The query contract continues to affect dense retrieval configuration identity
  only, not dense index identity.
- CUDA FP16 and CPU ONNX FP32 remain the only qualified profiles. There is no
  fallback, hot switching, second runtime, model download, or profile routing.
- Gold pooling retains all six distinct retrieval arms, candidate identity and
  provenance checks, and complete-six-arm-or-fail reviewability semantics.

## Failure diagnostics

Pooling outcomes may persist the failing retriever, a bounded stage identifier,
and a bounded exception category. They must not persist proposed query text,
document text, credentials, or unrestricted exception messages. A failed arm
continues to fail its case; diagnostics do not make the case reviewable.

## Qualification and evidence boundary

Implementation tests must exercise the qualified factory routing and both
production adapters, including invalid prompt registries and raw-query
regression. A local retrieval integration must demonstrate that the query-prompt
arm can contribute candidates while preserving all six arms.

CPU ONNX prompt qualification must report its exact reference execution, sample
identity, numerical metrics, and thresholds. If the required reference
execution or model artifacts are unavailable, the result is unqualified and
must be reported as such; helper-level behavior alone is not scientific
qualification. No real Quick Play operation, campaign rerun, or reuse of the
consumed live operation is authorized by this amendment.
