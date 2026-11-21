# Seneca — Rich Small-Pool CPU Batching Execution

**Independent review disposition:** Experimental design accepted. Authorize the Rich small-pool batching experiment only.

Research baseline: `71bff228c4e98098c61782e5a3bab6c6c1e7e2e3`

Canonical protocol:\
`docs/research/bge_quality_latency_frontier/evidence/small-pool-design/PROTOCOL.md`

Use the protocol's four treatment arms, four counterbalanced blocks, and predefined performance and scientific-parity gates without changing them.

## Execution authority

Authorize exactly 20 isolated assembler calls, consisting of four warm-ups and 16 measured calls.

Before execution, verify the available VM maintenance window, original deployed image, approved models, scientific settings, Rich workspace snapshot, storage isolation, Qdrant ownership and restoration procedure.

If the remaining VM lifetime is insufficient for the entire campaign plus bounded restoration, stop before any maintenance changes. Do not shorten the experiment to fit the window.

Preserve Torch FP32 `2/2`, the approved BGE checkpoint, all ten candidates, the original source scope and the frozen Qwen3 profile.

Record all blockwise wall times, CPU-seconds, batch shapes, padding, resource observations and scientific-parity outcomes.

Require the protocol's predeclared logit tolerance, exact candidate-score association, full ranking identity, anchor identity, evidence selection and packed-context identity.

Do not conceal or discard failed arms.

Restore and verify the original Seneca deployment before reporting.

## Reporting and repository persistence

Extend *The 59-Second Retrieval* with the completed experiment, raw measurements, charts, interpretation and limitations.

Preserve the full authorization prompt, Codex execution response, runtime identity, numerical observations, test outputs and restoration evidence.

Commit and push the results to a separately reviewable research branch.

Do not execute the Recipes BGE-15 experiment under this authorization.

No production deployment, model change, reranker policy change, publication migration or merge to main is authorized.

**Stop after the Rich experiment and report. VM has just been started&#x20;**
