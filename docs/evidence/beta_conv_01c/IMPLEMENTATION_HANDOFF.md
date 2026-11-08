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
translation language. The UI offers answer actions only for answered turns
inside the existing six-pair / 12,000-character window. Transcript actions are
hidden in Training Mode so they cannot bypass answer-reveal behavior.
Recent-conversation summary submits that same bounded window and is unavailable
when it is empty; the UI and synthetic user turn describe it as a bounded
recent-window summary.

Each completed action response is paired with a fixed synthetic user turn. The
executor receives only the selected visible answer or the bounded recent
conversation, plus an application-owned instruction. It does not retrieve
sources or produce citations. Truncated model output is discarded. Durable
trace provenance identifies conversation origin and the executor prompt
contract. Action history and exports carry no selected-source evidence scope.

## Accepted boundaries and limitations

- Natural-language transformation routing remains unsupported; typed requests
  continue through the canonical v1 resolver and grounded pipeline.
- First-turn greetings and capability questions retain current grounded
  behavior.
- A typed request such as “summarize this conversation” is not a supported
  natural-language operation.
- Actions can target only answers still in the bounded recent window.
- Transformations of grounded answers operate on their visible answer text and
  do not retain citations. Results are labeled as not re-checked against
  sources.
- Mixed source-plus-conversation transformations and whole-corpus analytical
  synthesis remain unsupported.
- Citation-preserving translation is deferred; it may translate answer blocks
  while retaining their existing citation references deterministically.

## Verification status

Synthetic backend and UI regressions cover explicit operation validation,
target selection, bounded history, synthetic-turn chaining, grounded follow-up,
no-retrieval behavior, transcript provenance, export labeling, and truncation
handling. Focused verification completed with 58 backend/generation tests and
35 UI tests passing. Targeted Ruff, ESLint, Python compilation, and
`git diff --check` pass. The UI project-wide typecheck remains blocked by five
existing errors in the unchanged `slice16k_r04_cuda_oom.test.tsx` fixture. One
existing generator test was excluded from the focused pass because its expected
network-policy message does not match the current `public_endpoint_forbidden`
result; it does not exercise conversation actions.

The configured model endpoint is available, but the required real-model product
sequence could not run against the existing workspaces: the
canonical API rejected the grounded source query with HTTP 409 and safe reason
`lexical_config_stale` before model inference. A direct conversation-action
request was also rejected before generation while validating the published
workspace snapshot. No workspace was reindexed or otherwise mutated to work
around this. Human product acceptance therefore remains pending a valid
published workspace for the canonical smoke. The successful model-list probe
does not count as model execution.

Implementation review is requested after the candidate commit is pushed.
Promotion, learned-router activation, and BETA-CONV-02 remain unauthorized.
