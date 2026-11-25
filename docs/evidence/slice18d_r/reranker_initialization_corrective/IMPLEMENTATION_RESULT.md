# 18D-R reranker lazy initialization corrective

- Branch: `corrective/18d-r-reranker-initialization`
- Implementation: `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`
- Parent: `155ccf0cff57010fd926655676da9c318208cfac` (verified against the Docling corrective branch)

## Investigation

ApplicationRuntime.start constructs one reranker in ProcessResources.
QueryRuntimeCache acquires and builds snapshot wiring under its own lock,
then returns a handle. Every snapshot wiring uses the process-owned
reranker. The synchronous conversation handler can run on multiple workers.
The cache lock is outside the scoring path. Previously two requests could
both observe an empty instance and enter from_pretrained concurrently.
Single worker-thread success does not test this overlap.

The locally installed locked Transformers implementation calls
no_init_weights and init_empty_weights during model construction. The former
changes module-level state and temporarily patches torch.nn.init functions.
Overlapping model loads can therefore also interact with unrelated loaders
in the process, such as a separate Gold authoring reranker or a lazy embedding
loader. This corrective serializes first use of the shared
reranker instance. It does not coordinate distinct model loaders or prove
that overlap caused either observed HTTP incident. The meta integrity guard
is effective regardless of the source of unmaterialized weights.

## Corrective

The per-instance lock covers loading and validation on first use. The
tokenizer and model are published as one tuple once device transfer and
parameter/buffer integrity succeed. Failed attempts leave no published
state and a later caller can retry. Cached calls return before acquiring
the lock. Model identity, CPU/CUDA selection, tokenizer inputs, query
length checks, inference mode, raw logits, and result order are preserved.

Technical paths are `src/offline_rag/rerank/cross_encoder.py` and
`tests/unit/test_cross_encoder_initialization.py`. The evidence is confined
to this directory. The Dockerfile, dependency lock and configuration match
the parent.

## Qualification

- `pytest -q tests/unit/test_cross_encoder_initialization.py tests/unit/test_hybrid_rerank.py` with the existing local environment: 15 passed. Deterministic thread events establish overlap without a real checkpoint. Tests use real Torch meta tensors for parameters and buffers before and after device transfer.
- Targeted Ruff lint and format, Python compilation, `git diff --check`: PASS.
- Existing conversation suite with local tokenizer fixtures and fake providers: 41 passed, 1 dependency deprecation warning. The initial run had 27 skips before those fixtures were supplied.
- Production-equivalent HTTP smoke: ENVIRONMENT_BLOCKED. This checkout has
  local model artifacts but no qualified isolated indexed workspace and
  authorized generation endpoint for a complete real HTTP query. The review
  VM is outside the execution scope for this corrective. Run the prescribed
  HTTP smoke after authorized cutover.

## Exact image qualification

```bash
sha=9c92e706c4b9e9d9ac0816a655bdf131cc63fca1
tag="seneca-review:${sha:0:12}"
docker build -f deploy/Dockerfile --build-arg SENECA_DEPENDENCY_PROFILE=cpu-release --build-arg SENECA_SOURCE_SHA="$sha" -t "$tag" .
python scripts/verify_docling_runtime.py "$tag" "$sha"
```

- Build: PASS. Image ID `sha256:8d45e633fac9b82a833a59117064c074759e317563a0bdb0cca87179986ee9a1`, size 2,635,983,378 bytes. Revision label matches the implementation SHA and the profile is `cpu-release`.
- Real BGE CPU scoring: PASS. The runbook smoke was executed inside that final image, with one Python worker thread calling the real `score_pairs` path. The accepted checkpoint was mounted read-only, with `--network none`. Artifact validation, first-use initialization and device transfer succeeded and returned one finite raw logit for one synthetic pair.
- Inherited Docling verifier: PASS. Image contract, 42 OpenCV shared objects, OpenCV and TableFormer imports.
- VM runbook shell syntax: PASS. No VM deployment or promotion was performed.
