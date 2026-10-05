# Slice 15H — Integration acceptance / closeout evidence

Status: **15H IMPLEMENTATION / EVIDENCE CANDIDATE**  
**INDEPENDENT REVIEW PENDING**  
**NOT YET ACCEPTED**

Do not treat this document as Slice 15 COMPLETE / ACCEPTED.

## Authority

| Item | Value |
| --- | --- |
| Architecture authority | `docs/slice15_developer_api_packaging.md` |
| Authority SHA | `6583fb3be64f2c66e8655b8b99166c358f8f0844` |
| Accepted implementation plan | `docs/slice15_implementation_plan.md` |
| Expected 15H baseline / starting SHA | `b6fe122a34367b39f44405012f022971cc53d858` |
| Accepted 15G implementation | `140350b8cc6eec6a2491c0a1696042e65b2d2b7e` |
| Candidate SHA | *(fill after commit; see git tip of `implementation/15H-integration-closeout`)* |

## Governance after baseline

- 15A–15G COMPLETE / ACCEPTED
- 15H AUTHORIZED / OPEN (this candidate)
- Slice 16–18 PLANNED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED
- Milestone 7 IN PROGRESS / closeout NOT AUTHORIZED
- Image optimization issue #1 remains deferred

## Environment

- Host: WSL2 Linux, Docker available
- Deterministic tests: FakeEmbedder / FakeReranker / fake generator client
- Container smoke:
  - Diagnosis/replace/persistence: `offline-rag:15g-test` (`8f4fc56c657d…`)
  - Candidate rebuild: `offline-rag:15h-test` image ID `623e2fa7ffc9` (~10.3GB; issue #1 deferred)
- Container user: `10001:10001`
- Mounts: `/data` RW (tmp world-writable), `/models` RO (repo `models/`)
- Strict offline env: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `OFFLINE_RAG_STRICT_OFFLINE=true`

## Exact test commands

```bash
pytest -q tests/unit/app/test_slice15*.py tests/unit/test_cli.py tests/unit/test_chunk_cli.py
pytest -q tests/unit/app/test_slice15h_integration_closeout.py
ruff check src/offline_rag/cli.py src/offline_rag/app/ingest_upload.py \
  tests/unit/app/test_slice15h_integration_closeout.py \
  tests/unit/test_cli.py tests/unit/test_chunk_cli.py
git diff --check
# Full suite (includes known pre-existing failures outside Slice 15):
pytest -q
```

## Test results

| Suite | Result |
| --- | --- |
| Slice-15 unit + updated CLI tests | **199 passed** |
| 15H closeout harness | **14 passed** |
| Ruff on 15H touched files | **clean** |
| `git diff --check` | **clean** |
| Full `pytest -q` | **1087 passed, 13 failed** (see exclusions) |
| Full `ruff check src tests` | **85 pre-existing findings** (not introduced by 15H; touched files clean) |

### Full-suite exclusions (not counted as 15H pass)

Pre-existing / out-of-scope failures observed on this tree (not caused by CLI→app migration):

- `tests/unit/test_slice12b_recovery_runtime.py::*` — `check_ready` kwarg mismatch in mocks
- `tests/unit/test_grounded_generation.py::test_eval_query_operational_outcomes` — same class
- `tests/unit/test_slice13b_authoritative_wiring.py::test_authoritative_pin_mismatch_fails_preflight_without_q3_writes` — sealed campaign residue on disk

CLI regressions introduced by product ingest were fixed in-tree (`test_ingest_json_txt`, `test_chunk_cli` scientific seed).

## CLI migration evidence

### Ingest

- Adapter: local path discovery (`discover_sources`) + `spool_local_files` → staging
- Mutation: `ApplicationRuntime` → admit ingest → `run_product_replace_ingest`
- Forbidden paths removed from `cmd_ingest`: direct `run_ingestion(...)`
- Tests: `test_cli_ingest_uses_app_layer`, `test_cli_source_forbids_scientific_bypass`, `test_spool_local_files_feeds_product_ingest`

### Query

- Adapter: `ApplicationRuntime` → admit query → `run_product_query`
- Forbidden paths removed from `cmd_query`: `GroundedAnswerOrchestrator` construction
- Presentation limited to product fields (`ProductQueryResponse.as_dict()`)
- Tests: `test_cli_query_uses_app_layer`, source AST guard

## Deterministic integration harness

File: `tests/unit/app/test_slice15h_integration_closeout.py`

Covered:

- Startup health live/ready
- First full-replace ingest → documents → query → trace
- Read-during-ingest snapshot pin (N visible while N+1 held post-lease)
- Replace inventory (A removed; B/C present) + post-replace query coherence
- OpenAPI exact product path set
- D08 evidence matrix completeness + representative HTTP envelopes
- Strict-offline missing embedding asset → `runtime_not_ready` (no download)
- Secret non-leakage (health/error/trace/logs)
- Query overload fail-fast (`service_overloaded`, no trace)
- Drain rejects `/v1/*` while `/health/live` remains 200

## OpenAPI path set (accepted)

```
/health
/health/live
/health/ready
/v1/ingest
/v1/query
/v1/documents
/v1/documents/{document_id}
/v1/trace/{trace_id}
```

Confirmed absent: `/eval/*`, unversioned `/ingest`/`/query`, chat/history, snapshot selection, mode selection, debug/admin product routes.

## D08 evidence matrix

See `D08_EVIDENCE` in `tests/unit/app/test_slice15h_integration_closeout.py` (complete catalog mapping: HTTP status, retryable, evidence location). Representative HTTP cases exercised in 15H + prior 15A–15F suites.

## Readiness-503 diagnosis (mounted `/models`)

**Classification: A — environment/provisioning problem**

Observed with models mounted RO and generation approvals set:

1. `/health/live` = 200, `/health/ready` = 503 `runtime_not_ready`
2. `validate_global_startup_requirements` **PASS** (Docling, tiktoken, generation approval OK)
3. Embedder/reranker construction **FAIL**:
   - `Permission denied` reading `/models/embeddings/.../offline-rag-embedding.json`
   - `Permission denied` reading `/models/rerankers/.../offline-rag-reranker.json`
4. Host file mode was `0600` owned by UID 1001; container runs as UID **10001**
5. After `chmod a+r` on those manifests (and other previously non-world-readable model files), `/health/ready` = **200**

No product-code repair applied (locked contracts already fail closed correctly).

## Real-profile / container smoke

### Results (15g image + fixed model perms; candidate code not yet baked)

| Step | Result |
| --- | --- |
| `/health/live` | 200 |
| `/health/ready` | 200 (after env perms fix) |
| Ingest N (a.txt,b.txt) | 200; `snap_bfe5146b85b17b204d0bb37a117941893dcab0e8b7dfb3e4dce383dde594394e`; document_count=2 |
| Documents | inventory matches N |
| Query (generator `host.docker.internal:11434`) | 502 `generation_unavailable` (endpoint not actually serving; fail-closed) |
| Trace on that failure | `trace_7fffe84c6ff2466d9fcba26e670ac815` present |
| Replace N+1 (b.txt,c.txt) | 200; `snap_af84b7ec19f887eb49dbc6b6b8b32251208357ba5d8753ac881d948f4cbb4dc0`; a.txt omitted |
| SIGTERM | Shutting down → Application shutdown complete → Finished server process [1] |
| Restart same `/data` | published N+1 inventory remains coherent |

### Real generator attempt

Restart with approved LAN endpoint `http://192.168.2.140:8888/v1` / model `qwen3.6-35b-a3b`:

- Persistence after restart: **PASS** (same `snap_af84…` inventory, a.txt still omitted)
- Product query: **502 `generation_unavailable`** with durable `trace_c3acada4df304bcabf9b91fc5cde7aff`
- Classification: **A / environment** — approved local generator not reachable from the container network path used in this smoke (fail-closed product behavior; not a Slice-15 contract defect). No cloud fallback used.

### Docker rebuild

`docker build -f deploy/Dockerfile -t offline-rag:15h-test .` — **PASS** (regression rebuild; not image-size work).

| Check | Result |
| --- | --- |
| Build | succeeds (`623e2fa7ffc9`, ~10.3GB) |
| User | `10001:10001` |
| CMD | `["python","-m","offline_rag.api.server"]` |
| CLI bake-in | product ingest/query use app layer (inspected in image) |
| `/health/live` / `/health/ready` | 200 / 200 (with readable `/models`) |
| Ingest smoke | 200; `snap_6b6b95d3…`; document_count=2 |
| SIGTERM | Shutting down → Application shutdown complete → Finished server process |
| Model weights in image | not embedded (mount-only) |

(~10.3GB CUDA image size remains deferred debt / issue #1.)

## Deviations

- Real answered query against LAN generator may be environment-limited; deterministic path covers answered query + citations via fakes.
- Full-repo Ruff noise pre-exists; 15H gate is clean on touched files.
## Residual risks

- Host-provisioned model trees with `0600` manifests will fail readiness under non-root container UID (operational footgun; document in deploy notes if accepted later — not a 15H architecture change).
- Concurrent CLI + API against same Qdrant Local store remains unsupported (D17).
- Product CLI ingest is full-replace; scientific additive ingest is no longer the product CLI path.

## Evidence locations

- Implementation: `src/offline_rag/cli.py`, `src/offline_rag/app/ingest_upload.py` (`spool_local_files`)
- Tests: `tests/unit/app/test_slice15h_integration_closeout.py`
- Legacy CLI test updates: `tests/unit/test_cli.py`, `tests/unit/test_chunk_cli.py`
- This document: `docs/slice15h_integration_acceptance.md`
