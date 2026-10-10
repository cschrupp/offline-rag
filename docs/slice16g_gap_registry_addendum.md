# Slice 16G gap registry addendum — Gold bootstrap + future answer feedback

Status: REGISTERED / NON-AUTHORIZING

Authority: `DOC-GAPS-REGISTER-AUTH-001`

This addendum:

- does **not** modify the frozen 16G-D0 design
  ([`docs/slice16g_gold_lab_games_pedagogy_design.md`](slice16g_gold_lab_games_pedagogy_design.md);
  blob `edc2be739621dbedfc44ed77861119a35f8f6d18`);
- does **not** authorize implementation of any registered item;
- registers discovered product/design gaps and a post-M7 planning candidate only.

Preserved (unchanged by this registration):

```text
GAP-16G-01: DESIGN REGISTERED / IMPLEMENTATION NOT AUTHORIZED
16G-I3: NOT AUTHORIZED
16H: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
Slice 17: NOT AUTHORIZED
Slice 18: NOT AUTHORIZED
M7 closeout: NOT AUTHORIZED
```

---

## GAP-16G-02 — Gold Baseline Bootstrap / Candidate-Generation Product Flow

```text
Identifier: GAP-16G-02
Title:      Gold Baseline Bootstrap / Candidate-Generation Product Flow
Status:     DESIGN REGISTERED / IMPLEMENTATION NOT AUTHORIZED
```

### Problem statement

Gold Lab currently:

```text
CAN:
  discover eligible pristine GoldAuthoringRun baselines
  create campaigns from those baselines
  perform human Gold adjudication
```

but the Seneca browser UI currently:

```text
CANNOT:
  create the pristine baseline that Gold Lab requires
```

Today the user must leave Seneca and use the existing CLI:

```text
offline-rag gold propose
offline-rag gold pool
optional: offline-rag gold prelabel
```

This is a **product-orchestration gap**, not a missing scientific subsystem.

### Existing authorities that must be reused

A future product flow **MUST** reuse:

| Authority | Role |
|---|---|
| Slice 9B | deterministic source sampling + local question/case proposal |
| Slice 9C | multi-retriever candidate evidence pooling |
| Slice 9D | optional advisory local prelabeling |
| GoldAuthoringRun | existing schema + persistence |
| Gold Lab | existing pristine-baseline eligibility resolver |
| Workspace publication | existing snapshot / corpus / chunk-set identity |

No second authoring pipeline.

### Expected future baseline-bootstrap flow

```text
Workspace / current publication
        ↓
Choose authoring proposal budget
        ↓
Generate candidate cases/questions
        ↓
Pool candidate evidence
        ↓
Optional advisory prelabel
        ↓
Validate pristine GoldAuthoringRun
        ↓
Expose as eligible Gold Lab baseline
        ↓
Create campaign
        ↓
Human adjudication games
```

Server/application layers remain scientific authority.
The browser is orchestration/presentation only.

### Registration-level invariants

```text
1. Machine-proposed questions/cases remain Silver.

2. No proposed case becomes Gold automatically.

3. Model prelabels remain advisory only.

4. Prelabels MUST NOT establish human relevance truth.

5. Baseline bootstrap performs no human Gold mutation.

6. Result MUST satisfy existing pristine-baseline eligibility.

7. Snapshot/corpus/chunk-set identity remains exact.

8. No filename/fuzzy/similarity migration.

9. No arbitrary browser filesystem path input.

10. No GoldDataset-v1 semantic change.

11. No automatic retrieval/model promotion.

12. No adaptive top-up / resampling policy for future 9G
    unless separately designed and authorized.
```

### Relationship to deferred Slice 9G

```text
Slice 9G:
DEFERRED / NOT AUTHORIZED
```

Registration of this gap does **not** reopen 9G.

When 9G is eventually authorized, the intended product path is:

```text
stable publication corpus
→ sufficiently large pristine candidate baseline
→ Gold Lab campaign
→ Question Check
→ complete 0/1/2 evidence adjudication
→ ~100–150 finalized production Gold cases
→ dev / held-out freeze
→ formal 9H
```

Do **not** freeze a proposal-count multiplier yet.
That belongs to future 9G design.

---

## NEXT-MILESTONE-CANDIDATE-01 — Answer-Level User Feedback / Continuous Evaluation

```text
Identifier: NEXT-MILESTONE-CANDIDATE-01
Title:      Answer-Level User Feedback / Continuous Evaluation
Status:     PLANNING REGISTERED
            DESIGN NOT OPEN
            IMPLEMENTATION NOT AUTHORIZED
```

Do **not** assign a new formal milestone number yet.

Milestone 8 currently exists as a historical stub, so this remains a named
post-M7 candidate until a future roadmap redesign gives it formal placement.

This candidate is **not** 16G implementation scope.

### Product objective

Allow users to give lightweight feedback on individual assistant answers
without interrupting the conversation, while retaining exact response
provenance so real product failures can later become reviewed evaluation
or regression candidates.

This feature is conceptually separate from:

```text
Gold Lab
GoldDataset
formal retrieval evaluation
generation semantic evaluation
Slice 17 deterministic Regression CI
```

### Candidate response-level UX

```text
Assistant response
────────────────────────────────────
answer text

citations / evidence

👍   👎
```

Selecting either reaction opens a small anchored/floating feedback popover.

A click on the thumb alone should **not** necessarily finalize/persist the
richer feedback form if the product chooses explicit submission semantics.

Preferred final action label:

```text
Submit feedback
```

**Not** `Accept`, because "Accept" could be confused with accepting the answer
as scientifically correct.

### Candidate thumbs-up feedback

Optional reason labels:

```text
Correct / useful
Well grounded
Good citations
Clear / concise
Other
```

Optional free-text field: `Anything else?`

No additional comment is required.

### Candidate thumbs-down feedback

Optional reason labels:

```text
Incorrect
Unsupported / citation problem
Missed relevant evidence
Incomplete
Irrelevant
Poor abstention / refusal
Hard to understand
Other
```

Optional free-text field.

The user must be able to submit a thumbs-down reaction without being forced to
write prose.

### External product-pattern references (non-authoritative)

Inspiration only — they do **not** define Seneca's future contract.
Do not claim API/schema compatibility with any of these products.

```text
Google Dialogflow CX:
  per-answer thumbs up/down;
  optional reasons for negative feedback.
  Reference: docs.cloud.google.com/dialogflow/cx/docs/concept/answer-feedback

Microsoft Copilot:
  thumbs up/down associated with individual responses.
  Reference: support.microsoft.com/.../get-started-with-microsoft-365-copilot-chat

OpenAI / ChatGPT:
  response-level thumbs feedback with optional follow-on issue details.
  Reference: help.openai.com/.../reporting-content-in-chatgpt-and-openai-platforms
```

### Candidate durable feedback event

Future design target, conceptually equivalent to:

```text
AnswerFeedbackEvent

feedback_event_id
conversation_id
turn_id
response_id
workspace_id

sentiment:
  thumbs_up
  thumbs_down

reason_labels[]
optional_comment

submitted_at
```

Bind the event to available exact answer provenance such as:

```text
trace_id
workspace_snapshot_id
model identity
generation contract identity
source scope
retrieval/config identities available from accepted product contracts
```

Exact schema remains future design territory.
Field names above are **not** frozen implementation contracts.

### Mutation / history principle

Preferred direction:

```text
append-only feedback history
+
effective latest reaction projection
```

Example:

```text
event 1: thumbs_down
event 2: thumbs_up

effective current reaction:
thumbs_up
```

Do not destructively erase prior provenance by default.
Final mutation semantics remain future design work.

### Candidate product metrics

Observational metrics only (no thresholds authorized):

```text
feedback coverage
= rated responses / eligible responses

effective thumbs-up rate
= current thumbs-up / rated responses

effective thumbs-down rate
= current thumbs-down / rated responses

negative reason distribution

citation-problem report rate

incorrect-answer report rate

missed-evidence report rate

poor-abstention report rate
```

Potential stratification:

```text
model/config identity
workspace/corpus
query category
time window
```

### Critical scientific boundary

```text
thumbs feedback != accuracy
thumbs feedback != groundedness
thumbs feedback != Recall@k / MRR
thumbs feedback != Gold
thumbs feedback != benchmark truth
```

User feedback is:

```text
OBSERVATIONAL PRODUCT EVIDENCE
```

not formal scientific ground truth.

Voluntary feedback is selection-biased and must not silently replace controlled
evaluation.

### Forbidden automatic transitions

```text
thumbs up/down → GoldDataset
thumbs up/down → automatic training example
thumbs up/down → automatic regression fixture
thumbs up/down → retrieval-default promotion
thumbs up/down → model promotion
thumbs up/down → benchmark-label mutation
```

### Future reviewed bridge to evaluation

Preferred controlled path:

```text
negative user feedback
        ↓
product feedback event
        ↓
triage / investigation
        ↓
candidate evaluation case
        ↓
explicit human review
        ↓
accepted regression fixture
```

Useful real-world failure discovery without contaminating formal Gold.

### Relationship to Slice 17

```text
Slice 17:
Regression CI
PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED
```

`NEXT-MILESTONE-CANDIDATE-01` does **not** become part of Slice 17 through this
registration.

Potential future relationship:

```text
answer feedback
→ discovers real failures

explicitly reviewed failures
→ may become regression fixtures

Slice 17
→ deterministically executes accepted regression fixtures
```

Continuous product feedback and deterministic CI remain different systems.

### Privacy / local-first direction

```text
Seneca should prefer storing feedback locally
and referencing already-durable turn/trace/provenance identities
rather than unnecessarily duplicating whole conversations.
```

Future design must explicitly define:

```text
retention
deletion
export
comments containing sensitive information
relationship to conversation deletion
```

Do not invent these policies in this registration.
