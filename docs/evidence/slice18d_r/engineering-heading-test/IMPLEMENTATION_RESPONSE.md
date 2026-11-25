# Engineering heading test correction

The accepted page renders the level-one heading `Engineering`. The test
expected `/Engineering summary/i` and failed with
`Unable to find role="heading" and name /Engineering summary/i`.
Commit `a0bcf887` on base `f2dd2bda1890fb86ddb055ef101c2e5e098eba43`
changes only that assertion to `{ name: "Engineering", level: 1 }`.
The page and production UI behavior are untouched.

From `ui/`, the focused `npm test -- src/test/slice16h_integration_acceptance.test.tsx`
passed all 13 cases. `npm run lint`, `npm run typecheck`, `npm test`
(478 tests across 52 files), `npm run build`, and `git diff --check`
passed. The build reported a chunk-size advisory.

PR #3 run 44983174130 on `6900aeb33f063492ab6709a73707ed1e65e6ab8d`
passed backend checks and failed only the unchanged heading assertion
(477 frontend tests passed, one failed). The fix is submitted separately
to the 18D-R initialization integration line for independent review.
Both PRs remain unmerged.
