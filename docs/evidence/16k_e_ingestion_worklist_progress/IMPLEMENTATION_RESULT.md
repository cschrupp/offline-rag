# S16K-E Implementation Result

## Authority and lineage

- Authority: `S16-K-E-INGESTION-WORKLIST-PROGRESS-METRICS-UX-IMPLEMENTATION-AUTH-001`
- Accepted design: `docs/slice16k_beta_ingestion_readiness_design.md` at subject `0839b565cd60958141366048520236a71bf16fd0`
- Authorized base: `b7997115b1e14ee840f2abda5bac6ced9e758e3b`
- Branch: `implementation/16k-e-ingestion-worklist-progress-metrics-ux`
- Candidate identity: the commit containing this result artifact; exact SHA is in the independent-review handoff.

## Implemented scope

Pre-submit Add Sources staging now appends additional selections, deduplicates repeated local selections, shows selected count and raw upload bytes, lists individual files, supports per-file removal and Clear all, and associates supported-type/per-file errors with the affected row while keeping aggregate limits separate. Submission uses the final staged membership; changing membership after an ambiguous request abandons the prior intent before a new key is prepared. The UI uses extension-based PDF classification consistent with the server's validated extension mapping and leaves authoritative admission to the backend.

The TypeScript API contract now models the existing optional/null worklist and metrics projections, including dense execution, stage durations, and lexical facts. Operation progress presents the durable worklist, truthful active-document set, completed/total/remaining counts, expandable queue, progress, generated/reused embeddings, measured throughput when present, execution device, elapsed time, and expandable details. Successful source operations show available outcome metrics. Known safe failure/OCR information is shown from the durable worklist; FAILED and INTERRUPTED remain distinct. No ETA is fabricated when the backend does not expose sufficient inputs.

Backend observability and operation schema: unchanged. Capacity/runtime policy, parser identity, ingestion semantics, and product limits: unchanged. 16K-F/G, Slice 17, and promotion: not authorized and not performed.

## Changed paths

- `ui/src/api/types.ts`
- `ui/src/components/OperationProgress.tsx`
- `ui/src/features/workspaces/uploadStaging.ts`
- `ui/src/pages/WorkspacePage.tsx`
- `ui/src/test/slice16k_e_ingestion_worklist.test.tsx`
- `docs/evidence/16k_e_ingestion_worklist_progress/IMPLEMENTATION_RESULT.md`

## Validation

- `npm test -- src/test/slice16d_b1_upload.test.tsx src/test/slice16c.app.test.tsx src/test/slice16i_operation_progress_telemetry.test.tsx src/test/slice16k_e_ingestion_worklist.test.tsx` — PASS, 34 tests across 4 files.
- Targeted ESLint for all changed TypeScript/TSX files — PASS.
- `npx vite build` — PASS; emits the existing large-chunk advisory (>500 kB).
- `git diff --check` — PASS.
- `npm run lint` — BLOCKED by pre-existing `react-hooks/set-state-in-effect` findings in unrelated Gold Lab files.
- `npm run typecheck` and `npm run build` — BLOCKED by pre-existing TS2352 in `ui/src/test/p4_human_uat_duplicate_message.test.ts:38`, whose partial `Operation` fixture omits required fields. The error is outside the changed files.

No backend tests or scientific/corpus executions were performed because backend code and scientific behavior were not changed.

## Review readiness

Implementation is complete within the authorized scope and is ready for independent review. The tracked worktree must be clean after committing the listed paths; unrelated pre-existing untracked user data remains untouched.
