# Seneca Knowledge Memory — implementation design proposal

This supplement describes how the original four-category architecture and workspace mockups could work against Seneca main at `5a703277`. The product goal is for Rich to resume learning in a new conversation, recognize his own contributions, and check current procedures against the selected manuals.

**Memory provides continuity. Sources provide factual authority.**

## Two paths through the workspace

```mermaid
flowchart LR
    M[Workspace memories] --> R[Recall a topic or saved study aid]
    R --> H[Attributed learning history]
    R --> Q[Resolve what the learner means]
    Q --> G[Existing grounded query]
    S[Current selection and bound publication] --> G
    G --> A[Answer with current evidence or abstain]
```

The distinction matters even within a single response. “You saved this mnemonic” can be supported by a saved record. “The manual currently prescribes this procedure” requires supporting passages retrieved for this request. A link to a previously cited passage explains where a note came from. Only the canonical query can supply a citation for a new procedural answer.

## Records and ownership

Keep four categories. An **episode** records a learning event, a **semantic note** identifies a concept and its relationships, a **learning record** captures what the learner saved or corrected, and **derived knowledge** covers synthesized material such as study guides. Track origin separately on each item or constituent claim: source-grounded, user-provided, or generated. Saving a generated mnemonic records Rich's decision to keep it and preserves its generated origin. Discussion of a topic establishes exposure only. Mastery requires separate evidence.

Propose a workspace-local store beneath the existing application data root. A record has a stable ID, revision, workspace ID, category, origin, display text, normalized topic terms, creation time, and typed links to exact input revisions. Source-grounded entries also require the originating workspace revision, snapshot, source and document version, and the evidence IDs from the committed answer. Represent mixed-origin summaries as linked items. A citation's membership can be checked mechanically. Whether its passage supports an extracted paraphrase requires inspection or evaluation.

Use atomic workspace writes with expected-revision checks. Deduplicate a repeated save by its originating event and item identity. Preserve corrections as superseding revisions. Allow the learner to inspect, edit and forget saved items. Forgetting removes the text from recall and invalidates summaries that depend on it. Scope lookup and all link traversal to the owning workspace. Keep note bodies local by default. Any future use of an external resolver with saved text needs an explicit product and privacy decision.

## Write, recall and reconcile

1. **Capture.** In a workspace with memory enabled, capture the topic and source references after a grounded turn commits. Extract candidate concepts from that completed exchange. Prefer source labels and exact terms for the first pilot. Store generated interpretations with their parents. Support explicit save for personal notes and generated aids through the existing workspace UX. Cancellation or a failed scientific commit produces no completed-learning event. A failed memory write leaves the committed answer usable and a save retry idempotent.
2. **Recall.** Read within the active workspace, match indexed topics and exact acronym strings, then follow bounded links. Return the user's wording for an explicitly saved mnemonic. Label study summaries with origins and links to their inputs. Ordinary factual questions continue through the existing turn orchestrator. Memory may supply topic or acronym hints for reference resolution. Pass only the resulting retrieval question into the existing snapshot-bound query. A memory ID is never a permissible document citation.
3. **Reconcile.** Resolve the current selection and published backing on every factual turn. A source revision makes the previous note historical for that publication. Preserve its original lineage and link a new revision only after current evidence supports it. Deselection immediately excludes that source from factual support, including via derived summaries. A discussion-history request can acknowledge the saved event. If no eligible evidence supports a procedural question, use the existing insufficient-evidence response and offer to reselect an applicable source.
4. **Bound cost.** Use a local topic index and deterministic selection for the first pilot. Cap items examined, link fan-out and rendered tokens independently of saved-history size. Reserve space for the current question and canonical evidence first. Drop optional memory detail when space runs out. Record counts, token usage and recall latency without recording private text. Choose numerical budgets from a small pilot measuring both exact acronym recall and added CPU latency. FlexA-Mem motivates budgeting at read time. A reduction in BGE forward time would need separate measurement.

The existing [prior-turn validator](../src/offline_rag/app/conversation/prior_turns.py) caps caller-supplied history at six exchanges and 12,000 characters. Cross-session recall should work with empty prior turns. The [turn orchestrator](../src/offline_rag/app/conversation/turn.py) already resolves scope and runs the bound snapshot query under lifecycle ownership. Reuse it. The [conversation trace store](../src/offline_rag/app/conversation/traces.py) is privacy-minimized and expires records. Durable memory therefore needs its own retained, user-visible provenance independent of trace retention.

## Acceptance walkthrough

Use a synthetic training manual with two published versions, a second selected source that lacks the target fact, and a second workspace containing a similarly named topic. Give the versions distinguishable statements and evidence IDs. Predeclare the expected source, answerable claim and mnemonic before running the walkthrough.

| Step | Learner action | Observable pass condition |
| --- | --- | --- |
| 1. Acquire | Discuss the training topic with version 1 selected. | The workspace contains the episode, linked concept and version-1 evidence reference. An interrupted turn adds no completed episode. |
| 2. Synthesize | Simplify an acronym and save the resulting mnemonic. Repeat the save. | One saved aid preserves the exact letters, authorship and original concept links. The original terminology is still inspectable. |
| 3. Recall | Restart the application and open a fresh conversation with no prior turns. Ask what was learned. | The summary recalls the topic and exact aid with attribution. The other workspace cannot retrieve either record. |
| 4. Revise | Publish version 2 with a changed procedural statement, then ask about the procedure. | The current answer reflects the changed statement and cites its version-2 passage. The prior note still identifies version 1. Check the answer against the passage as well as checking IDs. |
| 5. Deselect | Deselect the manual, leaving only the insufficient source selected. Ask again. | Seneca abstains from the unsupported procedure and explains how to restore source coverage. A separate history request can still identify the prior discussion. Neither old citations nor the saved mnemonic leak the procedure into the factual answer. |

All five steps must pass together. Retain selected source IDs, snapshot IDs, record origins and revisions, citation membership, answer disposition, and reviewer assessment of support. A plausible summary alone cannot pass this scenario.

## Research references and their roles

| Decision | Reference and scope |
| --- | --- |
| Retain, recall and reflect | [Hindsight paper](https://aclanthology.org/2026.acl-demo.27/) and [implementation](https://github.com/vectorize-io/hindsight). Use its lifecycle as an architectural reference. |
| Categorize and link notes | [A-MEM](https://github.com/WujiangXu/A-mem). Preserve Seneca's explicit origin and revision on evolving links. [Mem0](https://arxiv.org/abs/2504.19413) supplies a complementary selective-retention precedent. |
| Fit history into context | [FlexA-Mem v1](https://arxiv.org/html/2610.33274v1) and [code](https://github.com/WujiangXu/Flex-Amem) describe immutable history and a per-call timeline with detail selected to fit the budget. [MemGPT](https://arxiv.org/abs/2310.08560) motivates bounded working context and persistent recall. |
| Reconcile changing knowledge | [Zep / Graphiti](https://arxiv.org/abs/2501.13956) provides a temporal precedent. Applicable publication and source selection determine authority in Seneca. |
| Consolidate and present | [RAPTOR](https://arxiv.org/abs/2401.18059) motivates hierarchical summaries. [NotebookLM](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/) provides a product precedent for source-linked study materials. |
| Evaluate | [LongMemEval](https://github.com/xiaowu0162/LongMemEval) informs extraction, cross-session reasoning, updates, temporal reasoning and abstention. The walkthrough adds Seneca's citation and workspace isolation checks. |
| Decide factual authority | [Seneca A2](slice16_amendment_a2_conversational_grounding.md) governs the answer and claim-level citations. |

## First implementation increment

Build the walkthrough as one vertical pilot through the existing workspace UI, conversation path and local storage. Start with inspectable topic links and explicit saves. Evaluate usefulness with Rich, citation support with the two fixture revisions, and bounded recall cost with increasing amounts of unrelated history. Use those observations to decide whether more elaborate extraction or compression earns its cost. The external systems are design references. Their benchmark results do not establish Seneca performance. This revision proposes design only.
