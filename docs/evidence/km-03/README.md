# KM-03 workspace knowledge synthesis

KM-02 and SOL findings F1–F4 closed through PR #8 at
`6db028fa7bbedad42644102adf1d5c6062d48b2d`. The merge preserves the
accepted corrective as its second parent. [Main CI](https://github.com/cschrupp/offline-rag/actions/runs/45736034845)
passed on that merge.

## Try the vertical slice

1. Enable memory in **Knowledge**. Ask “What is forcible entry?” and
   “What tools are used for forcible entry?” in separate conversations.
2. Start a fresh conversation and ask “What did I learn about forcible entry?”
   Seneca groups the related prior discussions under a readable topic and
   labels older publications. Capture preserves bounded excerpts from cited
   answer claims and the source name, version, snapshot and evidence IDs.
3. In **Knowledge**, open **Create a mnemonic study aid** and add one or
   more originals. Give each known concept as `Term — Definition`. You can
   link a related discussion as a reference. The definitions you supply
   remain learner-provided. If a definition is unknown, leave it out and
   mark the original incomplete.
4. Preview the cue and its original-concept coverage. Identical terms with
   identical definitions can share a cue. Conflicting definitions keep
   separate positions. Save the aid, then ask “Recall my saved study aid
   Entry practice aid” in a fresh conversation to recover its stored text.

Recall and composition use bounded SQLite lookups, recognized question
phrasing and deterministic excerpts. They add zero model calls. Recall
turns are labeled as learning history and stay out of persistent
conversation history, exports, transformations and resolver input.
Current factual questions continue through the snapshot-bound source
query. Replacing or deselecting a source never makes a stored aid eligible
as evidence for that request.

Study aids preserve the original coverage and referenced item revisions.
Forgetting a referenced item removes dependent aids. Retrying a save uses
the existing client idempotency mechanism. The topic and cue rules are
conservative. They require explicit phrasing and supplied definitions.

## Qualification

- The backend walkthrough used the existing deterministic application
  fixtures and the real HTTP routes. It verified exact aid recall after
  application runtime restart, duplicate save delivery, a new citation
  using source version 2, and abstention with the applicable source
  deselected. Current queries never received recalled text.
- **ALVESCOUP**, **WASSPOC**, and **WALLACE WAS HOT** were tested as
  unresolved names. Their actual expansions were unavailable. A separate
  controlled pair, **Fixture A** and **Fixture B**, tested complete
  coverage, an exact overlap and a same-term/different-definition case.
- The browser exercise used the running Seneca UI against the real HTTP
  handlers with deterministic inference fixtures. Only the two factual
  discussions invoked the grounded generator.
- [Forcible-entry recall](forcible-entry-recall.png)
- [Controlled mnemonic coverage](mnemonic-coverage.png)

The focused conversation backend suite passed 45 tests. The frontend
workspace, conversation, claim-citation and Training Mode regressions passed
58 tests. Production Python Ruff checks, ESLint, TypeScript and Git
whitespace checks passed.

## SOL synthesis corrective

- **Selected-source authoring.** Enter the original names with empty concept
  fields and choose **Find definitions in selected sources**. Seneca performs
  one canonical grounded lookup. A proposed definition must match a
  term/definition pair and the original name in its cited excerpt. For a
  short supported cue, one bounded generation call can suggest an
  initial-matched phrase. Unknown or unverified definitions remain incomplete.
  The verified rows retain their original source lineage. Learner edits to
  those rows are attributed to the learner. Manual preview and save remain
  deterministic.
- **Cumulative synthesis.** Ask “Synthesize what I learned about forcible
  entry” to use the configured generator on up to eight related saved
  concepts. The response lists contributing record identities, revisions,
  and prior-publication status. This path uses no retrieval. Ordinary
  learning-history recall and exact study-aid recall remain deterministic.
- **Structured revision.** Use **Revise study aid** to update the original
  concepts. The preview and save recompute cues and coverage. The save uses
  revision compare-and-set and updates the searchable text and title lookup
  in the same SQLite transaction as the revision and history. Generic text
  correction is rejected for a study aid.
- **Publication revision.** The fixture switched from a blue to an orange
  practice tag. The version-2 answer and cited excerpt contain the orange
  instruction. Learning-history synthesis labels the two older discussions
  as prior publication. After deselection, the remaining source does not
  support an answer and the grounded request abstains.

The corrective uses synthetic definitions and deterministic generator
fixtures. ALVESCOUP, WASSPOC, and WALLACE WAS HOT remain unresolved without
verified source definitions. Association against the bound citation excerpt
is deliberately conservative, so a clipped excerpt may leave a concept
unresolved.
