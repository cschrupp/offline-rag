# 16E — Engineering Evidence

```text
16E:
IMPLEMENTATION CANDIDATE /
HUMAN ACCEPTANCE PENDING

AUTHORIZED BASELINE:
5bfa43aad14b47f75bdc2c914cbe346f66225ff1

BRANCH:
implementation/16e-engineering-evidence

16D-C:
COMPLETE / ACCEPTED / SEALED

AMENDMENT A4:
ACCEPTED / LOCKED / SEALED

16F–16H:
NOT AUTHORIZED

SLICE 16:
IN PROGRESS / NOT COMPLETE

SLICE 17 / 18 / M7 CLOSEOUT:
NOT AUTHORIZED
```

## Objective

Read-only Seneca Engineering presentation of accepted scientific evidence and
architecture. One-way projection only:

```text
accepted frozen evidence
        ↓
human-reviewed presentation registry
        ↓
deterministic exporter
        ↓
versioned static evidence manifest
        ↓
Seneca Engineering (Evaluation / Architecture)
```

No evaluation execution from the browser. No `/eval/*` runtime API.

## Contracts

| Artifact | Contract |
|---|---|
| Registry | `seneca-engineering-evidence-registry-v1` |
| Manifest | `seneca-engineering-evidence-manifest-v1` |

Paths:

- Registry: `eval/presentation/accepted_evidence_registry_v1.json`
- Exporter: `scripts/build_seneca_engineering_evidence.py`
- Manifest: `ui/public/evidence/engineering-evidence-v1.json`
- Runtime request: `GET /evidence/engineering-evidence-v1.json` (static asset)

Manifest ID (byte-identical regeneration):

```text
engmanifest_d063642a25ceca842d716c5e2180144cb6c4734dd1b6269d37e610624a29caff
```

(If governance edits re-pin a source hash, regenerate and update this ID in the
same commit.)

## Evidence records

| evidence_id | family | authority | promotion |
|---|---|---|---|
| `retrieval.slice9hp` | retrieval | accepted | non_promotional |
| `generation.slice10e` | generation | accepted | non_promotional |
| `recovery.slice12c` | recovery | authoritative | disabled |
| `security.slice13b` | security | authoritative | non_promotional |
| `performance.slice14c` | performance | authoritative | non_promotional |
| `performance.slice14-level-c` | performance | authoritative | non_promotional |

Authority, promotion status, and claim_scope remain separate fields. Accepted ≠
production promoted.

## Source bindings

| evidence_id | source_ref_id | path | locator / role |
|---|---|---|---|
| retrieval.slice9hp | retrieval-report | `docs/pilots/slice9h_p_results.md` | §2 / §3 / §4 aggregates & sensitivity |
| generation.slice10e | generation-report | `docs/pilots/slice10e_generation_prompt_ab.md` | §3 self-judge; §7 positive full-22 |
| recovery.slice12c | recovery-disposition | `docs/milestone6_agentic_recovery_security.md` | header recovery DISABLED disposition |
| security.slice13b | security-disposition | `docs/milestone6_agentic_recovery_security.md` | 13B completed/fail fail-closed narrative |
| performance.slice14c | perf-14c-aggregate | `eval/results/performance_14/.../aggregate.json` | machine extract |
| performance.slice14c | perf-14c-run-manifest | `eval/results/performance_14/.../run_manifest.json` | machine extract |
| performance.slice14-level-c | level-c-report | `docs/milestone7_performance_ui.md` | §18 / §18.3 Level-C projection |

Pinned SHA-256 values live in the registry `expected_sha256` fields and are
re-verified into manifest `actual_sha256` on every export. Hash mismatch fails
closed.

## Machine extraction (14C)

Direct fields from committed `aggregate.json` / `run_manifest.json`:

- suite_id / run_id / config_id / executing_sha / machine_profile_id
- quality_by_variant (nDCG@10, MRR, Hit@1, Recall@10)
- by_variant latency p50/p95
- RAM RSS p50; VRAM availability
- model_ids / machine_profile subset / start_timestamp

No new scientific calculations. Comparison note is curated wording only:
“higher observed ranking quality with higher observed retrieval latency”.

## Exact vs approximate

- 14C machine-extracted values: `value_qualifier = exact`
- Level-C documented rounded values (≈ 50.83 s, etc.): `approximate`
- TTFT / decode / tokens-sec: `availability = unevaluable`, `value = null`

## Security / recovery presentation contracts

Security primary card leads with:

- Execution: Completed
- Campaign outcome: Fail — fail-closed
- Interpretation: required invariant unevaluable → fail-closed by contract
- Harness: Accepted

Recovery displays Evaluation Complete / Efficacy Insufficient / Product recovery
Disabled / LangGraph Deferred — no toggle.

## UI surface

- Routes: `/engineering/evaluation`, `/engineering/architecture`
- Global nav: Engineering (with Overview / Workspaces / Settings)
- Overview: bounded capability copy + Engineering evidence card
- Architecture sections: Product / Snapshot-data / Deployment + Deferred

## Validation evidence

16E-E1:

- `uv run pytest tests/unit/test_slice16e_engineering_evidence.py` — PASS
- `uv run ruff check scripts/build_seneca_engineering_evidence.py tests/unit/test_slice16e_engineering_evidence.py` — PASS
- `uv run python scripts/build_seneca_engineering_evidence.py` — PASS
- `uv run python scripts/build_seneca_engineering_evidence.py --check` — PASS

16E-E2:

- `cd ui && npm test` — PASS (full suite)
- `npm run lint` / `npm run typecheck` / `npm run build` — PASS
- `dist/evidence/engineering-evidence-v1.json` present after build

Manual browser smoke (Vite `127.0.0.1:5173`):

- Desktop Evaluation + Architecture loaded
- Engineering global nav present
- Security fail-closed semantics visible
- Approximate Level-C and Unevaluable metrics visible
- Static network: `GET /evidence/engineering-evidence-v1.json` only for Engineering data
- No `/eval/*` calls observed from Engineering
- Narrow ~390 px: page scrollWidth matched clientWidth; tables scroll inside wrap

## Scientific non-scope

Confirmed absent:

- `/eval/*` runtime API
- run-benchmark / scientific controls
- recovery enablement / LangGraph / NeMo
- 9G / formal 9H / base.yaml promotion
- RAG-path / conversation orchestration changes
- `PORTFOLIO_DEMO.md` updates
- Slice 17 CI workflows

## Implementation lineage (this candidate)

```text
AUTHORIZED BASELINE:
5bfa43aad14b47f75bdc2c914cbe346f66225ff1

16E-E1 evidence/exporter:
0d701082e6e78ef2f8a3aa57725edc1efd73b0d9

16E-E2 Engineering UI:
08b82a7f44cda6e0398293f47c248cd139fe2321

16E-E3 evidence/status:
(this documentation commit)
```

Do not self-accept. Independent review + human acceptance required.
