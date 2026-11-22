# PR #3 frontend CI reproduction

**Classification: pre-existing baseline failure. Hold merge.**

[Hosted run 44971589913](https://github.com/cschrupp/offline-rag/actions/runs/44971589913)
tested reviewed head `3a6317c51010de6242adf187554842de52ddf174`.
Backend passed. Frontend recorded 477 passing tests and one failure.
The failure is the heading assertion at
`ui/src/test/slice16h_integration_acceptance.test.tsx:137`.
Hosted Node and npm were 22.23.5 and 10.9.9.

Reproduced in independent base and head worktrees with the same local
Node 22.23.3, npm 12.2.0, dependency lock and Vitest 5.0.3.

```bash
cd ui
npm ci --no-audit --no-fund
npm test -- src/test/slice16h_integration_acceptance.test.tsx
```

| Worktree | Commit | Result |
| --- | --- | --- |
| PR base | `f2dd2bda1890fb86ddb055ef101c2e5e098eba43` | 12 pass, 1 fail |
| Reviewed head | `3a6317c51010de6242adf187554842de52ddf174` | 12 pass, 1 fail |

Both failed with `Unable to find role="heading" and name /Engineering summary/i`.
The test blob is `34433d9bd1eb9de76952052ad4716d5baebca0b0`, the page blob
`259fe55b7c8d7633c3768348e57f930cf527a44d`, and the lockfile blob
`dc47f15af61b5190aa8423e1114537e0e456512b` in both commits.
The entire UI diff between those commits is empty.

The smallest repair is a test-only update on the 18D-R integration line
to find the level-one heading with exact name `Engineering`.
The test passed all 13 cases with this temporary change at the base.
The temporary change was reverted. PR #3 includes no frontend edit.
Re-run hosted CI after the separate fix lands. The local demonstration
does not clear the hosted check.
