# Docling parser-stack corrective implementation result

**Authority:** `DOCLING PARSER-STACK CORRECTIVE`
**Scope:** dependency compatibility and parser regression qualification only
**Implementation branch:** `implementation/16k-large-source-capacity-post-l6-cuda-product-policy`
**Authorized base:** `d9ddc4cd54b3b3966bfae28044439378ddee031f`
**Implementation candidate:** `739c393d4fada86814ae8c2c309925b81d88e4fd`

## Frozen boundaries

- `docling==2.126.0` remains unchanged.
- `docling-parse` is pinned from `7.18.0` to `7.23.1`.
- `docling-core` resolves from `2.95.0` to `2.104.0`.
- `doclang` resolves from `0.7.3` to `0.8.0` as required by the core upgrade.
- Torch/CUDA and `pypdfium2==5.13.0` remain unchanged.
- Capacity policy, product limits, and parser backend selection are unchanged.
- PyPdfium2 remains a diagnostic/reference result, not the production backend.

The lockfile diff contains only the requested parser/core pair and its transitive
`doclang` resolution. No unrelated dependency changed.

## Canonical environment

The repository `.venv` was synchronized from the updated lockfile and verified
to contain:

```yaml
docling: 2.126.0
docling-core: 2.104.0
docling-parse: 7.23.1
doclang: 0.8.0
torch: 2.14.0
torchvision: 0.29.0
pypdfium2: 5.13.0
```

## Parser qualification

The exact Shupe source was parsed twice through Seneca's real
`DoclingPdfParser` in the canonical environment:

```yaml
source_bytes: 67199839
source_sha256: 1f22131a12fccfd0f5ecca9d6e84e7a4314720eeb2abef602be7ebe9932f7c54
run_1: PASS, blocks=884, warnings=0
run_2: PASS, blocks=884, warnings=0
parsed_artifact_id: parsed_fac9a48885932a8b4984ebe6609068c90a4d5e46e6bd39bac7aa6d89c66265e3
parse_config_hash: cfg_6ed29345aabcb41fa426b8ea5a8e42c073acebf24aded022a927eaf69dfdb5c9
serialized_result_sha256: e24dd841bace62e03063b90f5fc4bd958d0e3504395fb4fca10d2c78d6f00b0e
```

Both runs exited `0`; no native crash occurred. The previous `7.18.0`
canonical runs exited `139` on this exact source. The `7.23.1` overlay result
was diagnostic only; the passing qualification above uses the fully resolved
canonical stack.

## Regression corpus

The parser comparison used the existing fixture plus two existing PDFs (about
2 MiB and 24 MiB). The fixture and 24 MiB PDF were identical at Seneca level:
block/type distribution, page provenance, warnings, extracted text hash,
serialized result hash, parsed artifact identity, and parse-config identity.

The 2 MiB PDF retained page provenance and warnings but changed from 2,679 to
2,641 blocks. The detailed comparison attributes this to parser extraction
normalization and layout grouping: removal of repeated inter-word whitespace,
headings and labels grouped onto the same line, and several long text/code
regions split into more faithful blocks. This is a parser-output change, not a
loss of source bytes or page identity, and is covered by the existing Seneca
parser contract tests.

## Tests and checks

```text
16 passed — parser, ingestion, Docling-artifact, L3 path-contract, and text/Markdown regression suite
Ruff — repository baseline contains pre-existing findings; no new source files were changed
git diff --check — PASS
```

The broader managed-ingestion test invocation was attempted but did not return
a result in the available run window; it is not claimed as passing here. The
focused parser/ingestion suite above and the live full-product gate completed
successfully.

## Live full-product Shupe gate

The running API reported the post-upgrade runtime and profile-aware policy:

```yaml
health_ready: 200 / ready
active_device: cuda
profile_id: cuda_fp16_v1
large_pdf.effective_max_bytes: 94371840
embedding_state_before_ingestion: UNLOADED
```

The first multipart attempt was rejected before mutation because the raw vault
object name had no `.pdf` extension (`unsupported_source_type`). The corrected
request supplied `filename=shupe-large.pdf` and then completed successfully:

```yaml
operation_id: wop_d8e58c282a084ed6be06f4aef4125814
status: succeeded
workspace_revision: 16 -> 17
source_count: 16 -> 17
source_id: src_586e676bd429443992c53b7bbcefdd71
source_content_hash: 1f22131a12fccfd0f5ecca9d6e84e7a4314720eeb2abef602be7ebe9932f7c54
parsed_searchable_document_count: 17
shupe_child_chunks: 374
embeddings_generated: 374
embeddings_reused: 3725
embeddings_failed: 0
dense_device: cuda
dense_dtype: float16
publication: succeeded
```

Normal retrieval after publication returned `status=answered` with grounded
citations and the Shupe workspace revision 17. `/health/ready` remained
`200`/`ready`. The post-run kernel-log check found no `segfault`, OOM, or
`killed process` entry in the inspected tail.

## Boundaries and follow-up

```yaml
capacity_policy_changed: NO
product_limits_changed: NO
L5_evidence_changed: NO
scientific_capacity_execution: NONE
promotion: NOT AUTHORIZED
native_parser_process_isolation: FOLLOW-UP ROBUSTNESS ITEM
```

The dependency upgrade fixes the qualified Shupe crash fixture in the
canonical environment. It does not isolate future native parser faults from
the API process; parser subprocess isolation remains a separate robustness
work item.

## Terminal

```yaml
DOCLING PARSER-STACK CORRECTIVE
IMPLEMENTATION + QUALIFICATION COMPLETE
READY FOR INDEPENDENT REVIEW
```

## IR-001 narrow rework — parser identity and provenance

Independent review IR-001 accepted the dependency upgrade, Shupe crash fix,
and live product gate, and required the parser stack to participate in cache
identity. The original candidate `739c393d4fada86814ae8c2c309925b81d88e4fd`
is retained as historical provenance and is not the current candidate.

The corrective is based on governance tip
`32c04ae5a44b25cbb700f08f8d9f400c8270d82a` and changes the PDF parser
contract to `offline-rag-docling-pdf-v2`. The parser configuration hash now
includes the resolved distribution versions for Docling, Docling Core, and
Docling Parse, the actual default threaded Docling Parse backend identity, and
the OCR setting. Parsed-document metadata and PDF corpus `parser_environment`
persist the same provenance. TXT and Markdown parser versions and hash inputs
are unchanged.

For the exact Shupe source, the identity changes from the previously recorded
v1 values to these v2 values under the same resolved dependency stack:

```yaml
v1_parse_config_hash: cfg_6ed29345aabcb41fa426b8ea5a8e42c073acebf24aded022a927eaf69dfdb5c9
v2_parse_config_hash: cfg_2b13aaf5076a70a1f25b969422c704b2ecfc610b4987d7a19deb1d40617fe059
v1_parsed_artifact_id: parsed_fac9a48885932a8b4984ebe6609068c90a4d5e46e6bd39bac7aa6d89c66265e3
v2_parsed_artifact_id: parsed_62648d55da9721893b3b4936f4681089587f70379f631e727393f201938ced6c
```

The known 2 MiB regression output was replayed through persistence with its
captured old and new parser blocks. The old 2,679-block v1 artifact and new
2,641-block v2 artifact receive distinct IDs; the old artifact is not reusable
under the v2 identity, and the new 2,641-block artifact persists and reloads:

```yaml
old_parsed_artifact_id: parsed_c22ee61f66c4f0bfee351d041149e3e1a6c4af132964bd918bbb38ac83222f33
new_parsed_artifact_id: parsed_be0cac4e558ddd7e21d609ae5c5304bbf8d4532477b23cd2df3488286ff2337d
old_blocks: 2679
new_blocks: 2641
old_artifact_reused_by_new_identity: false
new_artifact_persisted_and_reloaded: true
new_artifact_sha256: art_175eb801ebcb8a52976c9c41862eb25a2c2cb9e2026edf29cf013dc3d8a8508f
```

The deterministic PDF fixture test parses twice under the v2 identity and
compares serialized output. The integration suite verifies the parser-stack
metadata in both the parsed document and corpus manifest. The identity unit
suite verifies a v1 cache miss, distinct artifact IDs, successful v2
persist/reload, and unchanged TXT/Markdown identity.

Corrective validation:

```text
15 passed — parser, ingestion, Docling-artifact, path-contract, and text/Markdown suite (including identity tests)
3 passed — identity tests rerun after the 2,679/2,641-block persistence case was added
Ruff on all changed Python files — PASS
git diff --check — PASS
```

The exact Shupe source had already parsed twice successfully on this resolved
dependency stack before the identity-only amendment. The amendment does not
change conversion or block normalization. A fresh standalone Shupe parse
attempt after the amendment did not produce a terminal result in the available
run window and is not claimed as a new pass. The prior successful parser runs
and live Add Sources gate remain valid evidence for the unchanged conversion
path; the v2 identity is verified directly from the same resolved package
metadata.

```yaml
IR-001 finding R1 — parser stack not identity-bearing: CLOSED
IR-001 finding R2 — persisted parser provenance insufficient: CLOSED
capacity policy / product limits: UNCHANGED
L5 evidence: UNCHANGED
promotion: NOT AUTHORIZED
```

Current implementation candidate:
`d97e2dc421328443c4d4678b3af19d706e392437`.

Current terminal:

```yaml
DOCLING PARSER-STACK CORRECTIVE
IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT RE-REVIEW
```
