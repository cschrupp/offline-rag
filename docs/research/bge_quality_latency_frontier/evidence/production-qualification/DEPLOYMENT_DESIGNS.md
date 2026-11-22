# Deployment and rollback options for later review

The existing PyTorch BGE-30 consecutive deployment remains the fallback.
No production change is proposed for execution under this record. The
two candidates have different compatibility and qualification requirements.

| Boundary | BGE-30 sorted-eight | BGE-15 sorted-eight |
|---|---|---|
| Implementation | Bounded scorer strategy, default consecutive, strict active-input and original-order restore checks, optional frozen conditional selector | Same qualified execution treatment plus explicit approved depth settings and validated settings-bound publication path |
| Scientific identity | Keep reranker semantic hash only if the existing reviewed score/rank/evidence contract is satisfied. Batch size and device are excluded today. Review this identity classification explicitly before any activation | input_k is semantic. Recompute reranker_config_hash and immutable snapshot ID from the new manifest. Do not reuse the 30-depth identity |
| Execution provenance | Record strategy/version, selector identity if used, checkpoint/tokenizer digests, batch policy and resolved threads, image/host/software identity and parity qualification reference | Same execution fields plus depth, new snapshot/hash and migrated workspace revision |
| Snapshots and workspaces | Existing published snapshot IDs and workspace revisions can remain when executing the same qualified science. No publication edit or re-ingestion | New immutable manifest, validated matching corpus, chunk, dense and lexical references. No re-ingestion if backing checks pass. A coordinated workspace/corpus publication change is required for opt-in scope |
| Docker | Same model bytes and release dependencies. Smaller padded tensors may change allocations, allocation reuse, added prepass, warm wall and CPU. Measure actual headroom under load | Same model bytes. Reduced pairs may cut CPU/wall work. Measure peak RSS and coexistence with Qwen3. Prefer a separate isolated pilot image/data copy, with one local Qdrant owner for each physical store |
| Rollback | Restore the previous image or revert the opt-in strategy flag atomically where supported. Smoke the same snapshot IDs and cited UI behavior after switching | Rebind the previous immutable BGE-30 publication and matching settings through an atomic reviewed transition. Restore the former image/profile, keep existing sources and advance workspace revision normally. Retain both manifests and rollback assets |

## Publication compatibility

The real copied store validated both depth publications on the same backing.
The registry still rejects a manifest whose reranker hash differs from its
active settings. An app process with one global settings object cannot
safely serve mixed depth-15 and depth-30 snapshot identities. The lowest
coupling first pilot, if approved later, is a separate nonproduction
deployment with an isolated copy and matching settings. Serving both
profiles in one process would need a separate accepted profile-binding,
cache-identity and authorization design. Never turn off current-config
validation. Never hand-edit workspace or manifest IDs or reuse one live
local Qdrant directory across processes.

For a later migration, use approved leases, validation and journaled
commit for a coherent corpus pointer and matching workspace revision.
Keep source/version lineage, recent history and in-flight immutable
bindings meaningful. Define reader compatibility during cutover,
including fail-closed mismatch tests, publication interruption and
recovery, exact historical provenance and reverse migration. A refresh
should reveal the true current snapshot. No workspace migration is
necessary for a qualified depth-30 execution-only opt-in.

## Operational gates and monitoring

Before either candidate can be enabled, qualify ordinary CPU Docker
startup, health, model artifact readability, CPU/thread limits, RSS,
host memory and swap at planned admission. Preserve the existing
failure and cancellation semantics, including no release of reserved
capacity while an abandoned worker still runs. If a lifecycle change is
needed for workspace concurrency control, authorize and qualify it
separately. Never use batching or depth reduction to mask a disconnect
defect. Validate shutdown, restart persistence and one authorized live
grounded response with citations after a later release approval.

For an opt-in pilot, preserve a baseline observation, then monitor per
profile and workload tier: admission wait and rejection, total and
stage wall time, CPU-seconds, memory headroom, failures and trace
persistence, deadline/disconnect and cancellation transitions, and
source/snapshot binding. Track answer, abstention and citation-validation
categories without using them as relevance labels. Use sampled independent
quality review only on approved data. Log hashes, coarse shapes and
counts, never passage text, raw request transcripts or credentials.
Set review duration, alert thresholds, stop conditions and rollback
authority before any activation. Roll back on a parity or scope
violation, quality regression, unbounded queue or an agreed resource/error
limit breach. Verify the restored settings, health, workspace binding
and source inventory. Retain original model, image and publication for
the entire rollback window.
