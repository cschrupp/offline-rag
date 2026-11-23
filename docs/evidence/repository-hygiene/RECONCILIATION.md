# Repository Hygiene and Artifact Reconciliation

**Work branch:** `prep/stage2-docker-transport`

**Starting commit:** `00a05817cee0567fb519d63da51267be939118d0`

**Scope:** repository/worktree/artifact custody only. No VM, deployment, merge,
or Stage 2 native submission was performed.

## Persistent checkouts

The canonical checkout remains `/home/user/projects/technical_rag`, on
`docs/slice18f-model-representation-scope`. The active Stage 2 worktree is
`/home/user/projects/technical_rag-stage2`, on the existing
`prep/stage2-docker-transport` branch. The move from `/tmp` used Git's
`worktree move`; its branch, commit, upstream, and Git metadata were checked.

Six linked worktrees remain: the canonical checkout, Stage 2 worktree, PR #3,
PR #4, PR #5 implementation, and the PR #5 supporting design lineage. Their
paths, branch identities, and heads were verified. The four review branches
are clean; the Stage 2 worktree contains only this hygiene change before its
commit. No new branch was created.

Two clean, unpushed BGE diagnostic clones were not reachable from fetched
GitHub refs. Their complete histories were saved as verified Git bundles in
the ignored persistent artifact directory and recorded in
`ARTIFACT_CUSTODY.json`; the temporary clones were removed only after bundle
verification. Their tips are `1d1f9aecffe9d1905c5678e824c7073b5e958106`
and `9066e62fb1c07ab915e4e8360742b66f469afe1e`.

## Recovered repository evidence

The worktree now contains sanitized, reviewable copies of the unique
retrieval-latency incident authorization/diagnosis, browser observation, and
Rich stage response under `docs/evidence/retrieval-latency/`; Stage 1
authorization, source, and execution logs under
`docs/evidence/bge30-length-sorted/pr3-follow-up/stage1/`; and the Stage 2
source-hash manifest under `docs/evidence/bge30-length-sorted/stage2-integration/`.
The Rich small-pool chapter was not embedded in the fetched report refs and is
preserved as a historical excerpt at
`docs/evidence/retrieval-latency/rich-stage/SMALL_POOL_BATCHING_CASE_STUDY.md`.
It links to the separately maintained research branch and does not change its
canonical report.

Credential-bearing lines and deployment/source identifiers were removed from
the committed incident copies. Private traces and packed-context outputs are
kept outside Git under the restricted local artifact directory. The report
does not expose their contents or hashes.

## Retained artifacts

The persistent ignored root is
`/home/user/projects/technical_rag/artifacts/retained/seneca/`. The committed
`ARTIFACT_CUSTODY.json` records each artifact's identity, size, hash, durable
path, and retrieval/use instructions.

- Stage 2 OCI image: 606,774,272 bytes; SHA-256
  `48084b824acd41126f54eb264d6ad63f4414be3239a23ed905edf864c50c3380`.
- `seneca-models.tar.gz`: 4,643,400,874 bytes; SHA-256
  `857fc87a733ae8988f91e74c863eebe4ce757cddfb43ceae7dbd8c86b5201f81`.
  Its tar listing was checked (316 members, 257 regular files); no workspace
  corpus documents were present. Byte-for-byte regeneration is not claimed.
- Exploratory BGE ONNX export: its artifact identity and all recorded file
  hashes are retained in the manifest and locally verified. It is not a
  production model selection.
- Four 18D-R review screenshots are retained with per-file hashes.
- Two complete Git bundles preserve the otherwise unpushed BGE diagnostic
  histories; their recorded hashes and tips are in the manifest.
- Restricted local records include one trace projection, two packed-context
  outputs, and a private archive of selected historical diagnostic scratch.
  These are mode-restricted, omitted from Git, and require privacy review
  before transfer.

## Branch reconciliation

The remote had 158 heads at the start and has 157 after cleanup. Exactly one
remote reference was retired:

| Branch | SHA before deletion | Basis |
|---|---|---|
| `implementation/slice18d-metrics-audit` | `8591aacc1810ba7265014c55a4d9327f7f755a02` | Same commit as canonical `main`; ancestor of `main`; no open PR, worktree, or protection; recoverable from `main`. |

No history was rewritten. The protected archive branch remains present at
`64b5883311338689f291f181e47686fc1a9e3906`. Open draft PRs #3–#6 and the PR
#5 supporting design lineage remain present at their audited heads:

| PR / lineage | Branch | Head |
|---|---|---|
| #3 | `feature/bge30-length-sorted-batching` | `6900aeb33f063492ab6709a73707ed1e65e6ab8d` |
| #4 | `corrective/18d-r-engineering-heading-test` | `fee6515102ac2f8d9944e83d8b3d705dba9e1625` |
| #5 | `corrective/workspace-conversation-lifecycle` | `239ecd1ef30a200e023d87284d807bb3c444abba` |
| #5 design support | `design/workspace-conversation-lifecycle` | `76fdf1984ad8b8a0c08893d74d75405f2f8d8625` |
| #6 | `integration/bge30-cpu-stage2` | `bb3f614188e95f9d83d3b0cccbf9452dac7f67e7` |

After fetch/prune, 116 of the 157 remote tips are ancestors of `main`; 41
non-ancestor tips remain preserved. No other branch was deleted.

## Workstation cleanup

Nine clean historical Git worktrees were removed after verifying their exact
heads were recoverable from fetched remote references and that none was an
open PR head. Two obsolete CPUOV worktrees were also removed after their heads
were verified as ancestors of `main`. Seven stale Git worktree metadata
entries pointing to already-absent directories were pruned. The active
Stage 2, PR, and canonical worktrees remain registered and valid.

An additional standalone `/tmp/offline-rag-18dr-corrective` clone was clean at
`b4b2c803578b9f09663d652ae95488d7fb1bf1ac`, exactly matching the fetched
`docs/cloud-deployment-memory-preflight` branch. It had only ignored build and
test caches. The clone was removed; the GitHub branch and persistent checkout
reference remain intact.

A 145-file Docling fixture directory was proven byte-for-byte identical to
files already in the retained model archive (1,438,568,513 bytes total) and
removed as a duplicate. Other exact Git-blob duplicates, duplicate browser
captures, redundant private trace copy, generated JS/bytecode, and scratch
path/index files were removed only after identity checks. Selected one-off
diagnostic scripts/logs that were not committed are preserved in the private
scratch archive; chapter drafts already embedded in fetched reports were
removed. The workspaces HTML capture was disposable browser scratch.

The opaque `/tmp/seneca-corrective-context` file and two credential files were
left untouched because their contents/purpose are not part of this cleanup.
Other projects' files and directories, including `.aws`, `.codex`, and
Wellplot, were excluded. No VM was started or contacted.
