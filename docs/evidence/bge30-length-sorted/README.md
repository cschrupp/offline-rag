# BGE-30 length-sorted batching

## Research disposition

The bounded research and native qualification program is **CLOSED**. Campaign
A established fixed-depth performance and parity; Campaign B established the
specified lifecycle behavior and restoration. No further campaign is planned
in this tranche. The result is workload-specific and does not imply a
universal speedup or a production latency guarantee.

The accepted native results are:

| Workload | Warm assembler change | Warm scorer CPU change | Finding |
| --- | ---: | ---: | --- |
| Recipes, 30 candidates | −41.6% | −46.0% | Material improvement with fixed-depth parity |
| Rich 2, 10 candidates | +1.7% | −1.0% | No material benefit; assembler was slightly slower |

Campaign A's complete results, identities, resource observations, parity
checks, rejected submissions, and restoration record are in
[`campaign-a`](stage2-driver/campaign-a-17e92e30222b76e4/CAMPAIGN_RESULT.md).
Its operative authority is retained in
[`Campaign A authorization`](stage2-driver/campaign-a-17e92e30222b76e4/AUTHORIZATION.md).
Campaign B's eight lifecycle outcomes and restoration record are in
[`campaign-b`](stage2-driver/campaign-b-7b95b124c4cd0906/CAMPAIGN_RESULT.md).
The Campaign B projection discrepancy is explained in the
[lifecycle event reconciliation](stage2-driver/campaign-b-7b95b124c4cd0906/LIFECYCLE_EVENT_RECONCILIATION.md).

Campaign A's 28 submissions produced three completed observations in each
workload/strategy cell; the 16 capacity rejections were retained and excluded
from latency calculations. Its fixed-depth parity gate passed. Campaign B
completed all eight lifecycle submissions with zero retries, and the original
service was restored and verified. The lifecycle campaign is not additional
performance evidence. These isolated four-vCPU results do not establish
production p95, a service-level objective, or behavior under untested
concurrency.

## Runtime behavior

`reranker.batching_strategy` accepts `consecutive` and `length_sorted_8`.
The supported default remains `consecutive`. The setting is an execution
strategy and is excluded from the reranker scientific configuration hash;
candidate depth, checkpoint, FP32 scores, raw-logit interpretation, tie-break,
source scope, and snapshot identity remain unchanged.

The CPU path uses the requested setting. CUDA continues to use
`consecutive`, including when the shared configuration requests
`length_sorted_8`, because sorted-eight has not been qualified on CUDA. The
effective and configured strategy are reported separately so operators can
verify this behavior. No deployment-specific implementation fork is used.

Both strategies use the pinned BGE checkpoint and tokenizer, FP32 inference,
the existing candidate depth and score contract, and passage-only truncation
at 1,024 tokens. Sorted-eight measures the actual truncated sequence lengths,
sorts by length and then original ordinal, scores batches of at most eight,
and restores scores to original candidate ordinals before canonical
raw-logit-descending / chunk-ID-ascending ranking. A tokenizer lock protects
its shared padding/truncation settings; it does not cover model forward. The
strategy remains outside the scientific fingerprint, and accepted snapshots
retain their identities. Campaign A required the existing per-logit tolerance
`abs(delta) <= 1e-4 + 1e-5 * abs(baseline)` plus exact candidate-score
association, ranking, anchor, evidence-unit, packed-context, and citation
parity. Near ties can still be sensitive to floating-point differences, so
parity remains an explicit gate for any future code change to this path.

Runtime telemetry is local application logging and retrieval metadata. The
`reranker_completed` event reports effective/configured strategy, device,
retrieval and scorer latency, input and returned candidate counts, and the
process lifetime RSS high-water mark when available. `reranker_failed` reports
failure type, candidate count, scorer latency, strategy, device, and the same
RSS measure. The RSS field is a process-lifetime high-water mark, not a
per-request memory peak. These fields do not alter the durable product trace
schema.

## Controlled CPU activation procedure

This procedure is prepared for a separately authorized, reversible
activation. The repository default remains consecutive; no activation or
merge is authorized by this document.

### Docker Compose

In the Compose `.env` file, set:

```dotenv
OFFLINE_RAG_RERANKER_BATCHING_STRATEGY=length_sorted_8
```

Build and recreate only the application service so the running process uses
the integrated code and setting:

```bash
docker compose -f deploy/docker-compose.example.yml build offline-rag
docker compose -f deploy/docker-compose.example.yml up -d --force-recreate offline-rag
```

Confirm readiness and inspect the local `reranker_completed` event for
`device=cpu` and effective `batching_strategy=length_sorted_8`. If the resolved
device is CUDA, the effective strategy must be `consecutive`.

### Workstation package

Install a workstation package built from the integrated source (the normal
builder is `scripts/workstation/build_package.sh`). Then add the setting to
`~/.config/seneca/workstation.env`, which is read by `seneca.service`, and
restart the user service:

```bash
systemctl --user restart seneca.service
```

Confirm service readiness and the effective strategy in the local application
log. The supported workstation package ships `config/base.yaml` with the
consecutive default and carries the same single application implementation.

## Rollback procedure

For Docker, set the Compose `.env` value to `consecutive` (or remove it; Compose
uses the consecutive default) and recreate the application service with the
command above.

For a workstation package, set
`OFFLINE_RAG_RERANKER_BATCHING_STRATEGY=consecutive` in
`~/.config/seneca/workstation.env` (or remove the line), then run:

```bash
systemctl --user restart seneca.service
```

In either case, verify health and confirm telemetry reports effective
`consecutive`. This rollback changes only runtime batching selection; it does
not migrate or rewrite publications or workspaces.

## Development validation

```bash
pytest -q tests/unit/test_cross_encoder_batching.py \
  tests/unit/test_cross_encoder_initialization.py \
  tests/unit/test_hybrid_rerank.py tests/unit/test_context_expansion.py
```

The separately retained research decision memorandum is linked from the
prior research revision at
[the production qualification decision memorandum](https://github.com/cschrupp/offline-rag/blob/27b1389654f7c89e72e98447bd81d34cc38b03fe/docs/research/bge_quality_latency_frontier/evidence/production-qualification/DECISION_MEMO.md).
Its historical results and the VM-specific diagnostic drivers/watchdog remain
evidence only and are not part of the production execution path.
