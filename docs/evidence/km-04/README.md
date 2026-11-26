# KM-04 — Workspace memory in Training Mode

KM-03 and findings F1–F4 are closed within controlled-fixture qualification. PR #9 was merged with its accepted head in the ancestry of [`4ad196d9`](https://github.com/cschrupp/offline-rag/commit/4ad196d9411868da1ed73006337bf7a0d9d0e36d). [Main CI passed.](https://github.com/cschrupp/offline-rag/actions/runs/45747583185)

## Integrated acceptance

`test_km04_integrated_memory_and_training_walkthrough` exercises the five steps against a temporary workspace and deterministic inference fixtures:

1. Two separate grounded discussions populate a shared forcible-entry topic with source provenance. A cancelled request adds no exposure.
2. A controlled two-mnemonic study aid preserves original definitions, learner attribution and coverage. Missing definitions remain unknown.
3. A new conversation recalls the topic and exact saved aid. Training Mode can create a flashcard and cloze exercise from a verified cited statement, then save misses, reveals, assisted matches and unassisted exact matches using deterministic operations. A second workspace stays isolated. A fresh application runtime can read the original workspace's saved data.
4. Publishing a revised source changes the factual response and citation to version 2. The old card and source-linked aid are flagged for revalidation, and previous matches are reported as historical.
5. Deselecting the applicable source produces a grounded abstention. The old card cannot be practiced against the new or unselected source. Pausing memory prevents new learning writes. Forgetting a card removes its dependent outcomes.

The running Chromium demonstration shows the [source-linked exercise and assessed recall](training-recall.png) and [the saved study aid](training-study-aid.png). The rendered UI used the application API and a deterministic fixture provider with synthetic text. Card creation was an explicit user action. Review, reveal, assessment and progress use the local workspace memory database. Recent activity and exact exercise matches do not establish topic mastery.

## Checks

- Backend conversation and worker ownership suites — 63 passed.
- KM-04, KM-01/02, and existing Training Mode frontend suites — 39 passed.
- Frontend lint, TypeScript and production build passed. The build reported its chunk-size advisory.
- Ruff lint and formatting checks passed for changed production Python files. Git whitespace check passed.

## Integrated validation and rollout

Use the existing locked build and workstation or CPU Docker release path. Verify the candidate in an isolated workspace with a disposable data root, the existing model mounts, and generation configured according to the existing deployment contract. Run the five-step walkthrough above with two distinct source revisions. Open **Training Mode → Review workspace memory** to inspect an aid, create a card, check and reveal an answer, and inspect provenance and review recommendations. Reopen the workspace after restart, repeat with a second workspace, and verify pause and forget. Qualify the runtime and provider on that environment before promotion.

Before upgrading an existing deployment, preserve the approved image or workstation release and take a consistent backup of its data root. Use the existing release rollback procedure if the integration fails, retaining a backup of any post-upgrade data. No production cutover was performed here. Rich's original ALVESCOUP, WASSPOC and WALLACE WAS HOT definitions remain an external acceptance dependency. The controlled fixtures do not establish coverage of those real mnemonics.

## Live validation and synthesis correction

The bounded workstation run used the CPU ONNX profile, provisioned models, and the configured OpenRouter model `~deepseek/deepseek-flash-latest` with synthetic documents in an isolated data root. The two grounded discussions took 5.691 s and 3.271 s and were grouped under the same topic. Cross-session lookup took 6 ms. Source-driven mnemonic generation verified four source-linked definitions in 4.974 s and did not supply definitions for the unknown fixture. Card creation took 2.081 s. Training assessments distinguished a miss, an exact match, a reveal, and an assisted match. The revised answer cited the orange form in version 2, while old materials became historical. Source deselection returned an insufficient-support abstention with recovery diagnostics. The saved aid survived process restart and recall reproduced its text exactly. The second workspace stayed empty, pause blocked recording, and forgetting removed the card and its outcomes.

The original synthesis request returned HTTP 502 in 3.281 s. An instrumented replay of the same discussions showed an upstream HTTP 200 with null content, finish reason `length`, and 512 completion tokens, all reasoning. The adapter rejected missing content before JSON or attribution validation. After adding a structured output request and allowing up to 1,200 output tokens within the configured cap, replay against the same provider stopped normally in 6.715 s. It used 438 prompt tokens and 654 completion tokens, 506 of them reasoning. The canonical parser accepted three paragraphs referencing both saved discussions. The synthesis connected the form's purpose to the inspection and filing sequence without adding new facts. Attribution still requires two distinct saved contributors and rejects unknown references. When synthesis is unavailable or unusable, the route offers deterministic saved-history excerpts without claiming verified synthesis or current factual authority.

The regression captures the observed null-content completion through the actual OpenAI-compatible adapter. It also checks fenced JSON with integer references and refusal of a reference outside the bound input set. The unaffected live workflow cases were not repeated. The earlier KM-04 browser evidence used a deterministic test provider. Rich's actual definitions still require user acceptance.
