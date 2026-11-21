# Publication preparation and rollback boundary

The deployed BGE settings use input_k 30, output_k 10, raw logits, FP32
on the CPU release and a separate context anchor_k 5. The semantic hash
includes input_k, model/revision/adapter, input construction, truncation,
max length, score transform and tie-break. It excludes execution details
such as batching and device, and excludes output_k. Hold both output_k
and context policy fixed. Bind sorted-eight to a separate experimental
execution fingerprint and require exact rank/evidence parity at each depth.

`CanonicalSnapshotManifest` includes `reranker_config_hash`. Computing
its ID from the entire manifest means a changed depth requires a new
immutable snapshot identity. With ordinary `resolve_snapshot()`, a
BGE-30 manifest in a BGE-15 runtime fails with `reranker_config_stale`.
A settings flip would leave existing workspaces pointing at incompatible
published snapshots. Never disable the current-configuration check.

## Safe isolated preparation

1. With authorized VM preflight and the original server stopped, make a
   consistent copy of the store. Verify original workspace revision,
   manifest, effective scientific hashes, scope, index identities, model
   artifacts and immutable source inventory. Open the copied Qdrant with
   a single owner and freeze the original manifest and pointer bytes.
2. Use a separate settings object with just reranker.input_k changed.
   Derive a new manifest from the existing one with a recomputed
   reranker_config_hash and new snapshot ID. Corpus, chunk, dense,
   lexical, embedding, fusion and context identities stay fixed. Verify
   their compatibility using the ordinary registry and actual artifact
   checks. The registry validates corpus/chunk linkage, dense collection
   existence/count, lexical backing and config identities. No re-ingestion
   or rebuild is needed if those checks pass.
3. Use the canonical registry publication API on the copy, with
   current-configuration validation enabled. The API writes the new
   immutable snapshot and atomically advances the **copied corpus**
   pointer. The old manifest remains addressable with its own settings.
   Leave the copied workspace record at revision 4 and use explicit
   server-owned admitted snapshot bindings for the diagnostic. Do not
   call the workspace HTTP route with a forged or stale workspace binding.
4. Resolve both snapshots by their own IDs using their respective
   settings against the same exclusive copied Qdrant owner. Check that
   each rejects with the other settings, that dense and lexical artifacts
   and source scope match, and that the original immutable manifest
   bytes are unchanged. Stop if any backing or config validation fails.
5. Run only the predeclared isolated matrix. Restore the original
   container and verify both health endpoints, image, mounts, restart
   policy, original workspace revision, original snapshot, and source
   inventory; discard the copy after verification.

The production registry currently binds to one runtime-wide settings
object. The existing immutable files can coexist, but the production
route cannot serve mixed BGE-30/BGE-15 workspaces under that one settings
object. Altering only a corpus pointer also cannot migrate a workspace,
whose read path binds the snapshot from the workspace record. The
snapshot journal is designed for controlled paired pointer/record
publication. An opt-in mixed-profile resolver or separate deployment
and isolated copy would need its own accepted design. Do not undertake
live migration or profile integration from this proposal.

## Rollback requirements, if a later release is authorized

Retain the BGE-30 image/configuration and immutable manifests, indexes,
models, and original binding identities. Switch back to matching settings
and rebind the previous scientific snapshot through a supported, atomic
workspace/publication transition, with a new workspace revision where
the contract requires advancement. Preserve source lineage and in-flight
snapshot bindings. No manual edits of canonical manifests or reset of
workspace revision. Verify existing 30-depth snapshot resolution, source
scope, grounded rendering, health and monitoring after rollback. Establish
migration, mixed-runtime support, telemetry and activation only after
both performance and quality justify the separate deployment design.
