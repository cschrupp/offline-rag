# BETA-CONV-01C — Explicit Conversation Actions

## Scope

Implementation starts from canonical `main` at
`7377871a5b96758129d2eb4e504a6b50c8d5162c` on
`feature/beta-conv-01c-explicit-conversation-actions`.

The 01B natural-language router remains archived at
`archive/beta-conv-01b-conversation-lane` (`d8ae2c9074bdd928a6599ec25dd9d9d2eb98f2b8`)
after its predetermined unseen-router safety gate returned NO-GO. 01C adds
application-selected transcript actions without changing typed free-text
routing or enabling the archived router.

## Product contract

The application exposes summarize-answer, simplify-answer, translate-answer,
and summarize-recent-conversation actions. The server validates the operation,
bounded alternating prior-turn sequence, target assistant index, and supported
translation language. The UI offers answer actions only for completed
`status=answered` responses inside the existing six-pair / 12,000-character
window, and maps those entries deterministically to assistant indices. The
server verifies history bounds and alternation, target index bounds, odd
assistant-turn position, assistant role, and the preceding user turn. Because
history is client-supplied, the server does not independently reconstruct the
original response status. This is the accepted beta boundary. Transcript
actions are hidden in Training Mode so they cannot bypass answer-reveal
behavior.
Recent-conversation summary submits that same bounded window and is unavailable
when it is empty; the UI and synthetic user turn describe it as a bounded
recent-window summary.

Each completed action response is paired with a fixed synthetic user turn. The
executor receives only the selected visible answer or the bounded recent
conversation, plus an application-owned instruction. It does not retrieve
sources or produce citations. Truncated model output is discarded. Durable
trace provenance identifies conversation origin and the executor prompt
contract. Action history and exports carry no selected-source evidence scope.
For conversation-origin actions, `snapshot_id` records the workspace's stored
snapshot state at action execution time. It is workspace-state bookkeeping
only: it does not mean the transformation read, validated, or was grounded in
that snapshot. This interpretation also applies to exported JSON. The UI does
not show the Current/Historical scientific snapshot badge for conversation-
origin responses; source-origin answers retain their existing badge.

## Accepted boundaries and limitations

- Natural-language transformation routing remains unsupported; typed requests
  continue through the canonical v1 resolver and grounded pipeline.
- First-turn greetings and capability questions retain current grounded
  behavior.
- A typed request such as “summarize this conversation” is not a supported
  natural-language operation.
- Actions can target only answers still in the bounded recent window.
- The synthetic user turns inserted for actions are fixed application strings.
  They are mostly English, except for Spanish-target translation, so Spanish-
  speaking users may see an English synthetic turn in conversation history.
- Transformations of grounded answers operate on their visible answer text and
  do not retain citations. Results are labeled as not re-checked against
  sources.
- Citation-preserving translation is deferred until after beta. A future
  implementation may translate grounded answer/claim blocks independently
  while deterministically retaining their existing citation references.
- Mixed source-plus-conversation transformations and whole-corpus analytical
  synthesis remain unsupported.

Other accepted beta boundaries are unchanged: free-text natural-language
transformation routing is unsupported; first-turn greetings and capability
requests retain current grounded behavior; typed "summarize this conversation"
is unsupported; answers outside the bounded action window cannot be
transformed; and whole-corpus analytical synthesis is deferred.

## Verification status

Focused corrective verification:

- Backend: 41 passed in `tests/unit/app/test_slice16d_b3_conversation.py`.
- UI: 18 passed in `ui/src/test/slice16d_b3_conversation.test.tsx`.
- Targeted ESLint and Ruff lint pass. The production action module passes Ruff
  format checking. The large pre-existing backend test file has formatting
  drift in its baseline; it was not reformatted wholesale. Ruff's existing
  `RUF059` findings in that test file remain excluded from this focused lint.
- `git diff --check` passes.
- The project-wide UI typecheck still reports five pre-existing fixture errors
  in the unchanged `slice16k_r04_cuda_oom.test.tsx` file.
- The Starlette TestClient emits its existing `httpx` deprecation warning.

### Dedicated real-model product smoke

The canonical API was started with the existing local configuration and became
ready. A dedicated workspace was created rather than changing any prior user
workspace. Its one synthetic source published successfully:

```yaml
workspace_id: ws_894d1092fba8440fa125f261f6340b27
revision: 2
snapshot_id: snap_ffd22a80eccf0e2376ca620fb574427d7bf499f4beeb0601b76b3df110bbe1c8
source: 01c-smoke-facts.txt
publication: SUCCEEDED
```

The source contains only synthetic Kestrel workshop facts. The pre-sequence
grounded question returned `answered`, `answer_origin=sources`, one citation,
and a query trace. The eight prescribed steps then completed through the
canonical API. The longer answer and its Spanish translation were used for
the translation-headroom check. All grounded turns returned source origin,
citations, and query traces; all explicit actions returned conversation origin,
no query trace, and no citations. The final recent-conversation action was
sent the latest six pairs (12 turns), not the entire longer transcript.

Representative observed outputs:

```text
Grounded baseline:
The Kestrel workshop opened in 2019.

Summarize:
The Kestrel workshop opened in 2019.

Simplify:
The Kestrel workshop started in 2019.

Spanish:
El taller Kestrel comenzó en 2019.

Back to English:
The Kestrel workshop started in 2019.

Long source-grounded answer:
The Kestrel workshop opened in 2019, operates an amber protocol that inspects
pumps every 45 days, has a test-container capacity of 18 liters, and maintains
inspection records using a blue ledger.

Long-answer Spanish translation:
El taller Kestrel se inauguró en 2019, opera un protocolo ámbar que inspecciona
las bombas cada 45 días, tiene una capacidad de contenedor de prueba de 18
litros y mantiene registros de inspección utilizando un libro azul.

Typed “Is that true?” follow-up:
The facts regarding the Kestrel workshop are verified as true: it opened in
2019, the amber protocol inspects pumps every 45 days, the test container has
a capacity of 18 liters, and the recordkeeping system is a blue ledger.
```

The meaning remained consistent across the sampled transformations, with a
minor terminology loss: “blue ledger” became “libro azul” (“blue book”) in the
long Spanish translation. No unsupported facts were added. This is recorded as
a translation-quality observation, not a prompt change or a claim of perfect
terminology preservation. The typed follow-up returned to grounded retrieval
with a query trace and one citation after the synthetic action turns. The
recent-window summary described only the supplied bounded conversation and
returned without retrieval, citations, or query trace.

Conversation action responses retained the workspace's stored `snapshot_id`
while remaining conversation-origin and citation-free. This is workspace-state
bookkeeping only, not evidence that those actions read or validated the
snapshot.

An initial smoke-runner request accidentally submitted eight pairs to the
six-pair endpoint and received the expected `prior_turns_too_many` HTTP 422
before model execution. No output was partially accepted. The smoke was then
run with the correct bounded window and completed; this was a runner input
correction, not an application or prompt correction. Sanitized step evidence
was captured at `/tmp/beta-conv-01c-live-smoke.json` in the execution
environment.

## Disposition at candidate handoff

The statements above describing review as requested and promotion as
unauthorized record the state when candidate `1103b1e9` was handed off. The
candidate has since received independent implementation and product-smoke
acceptance, followed by Human product acceptance. The accepted 01C branch has
been combined with the independently reviewed 01B closeout documentation for
the fast-forward promotion. Canonical `main` now includes the combined history
at `711dc1cb02499124e56116ab7cac7b3ea6b109db`. Learned-router activation and
BETA-CONV-02 remain unauthorized.
