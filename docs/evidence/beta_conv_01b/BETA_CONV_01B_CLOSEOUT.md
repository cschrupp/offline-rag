# BETA-CONV-01B — Natural-language Conversation Lane closeout

**Disposition:** `NO-GO FOR BETA / EXPERIMENT CLOSED`

## Preserved candidate

The exact 01B candidate is preserved without modification at:

```text
candidate: d8ae2c9074bdd928a6599ec25dd9d9d2eb98f2b8
feature branch: feature/beta-conv-01b-conversation-lane
archive branch: archive/beta-conv-01b-conversation-lane
```

The archive branch points to the same commit as the feature branch. The
candidate is experimental reference code and is not production code to merge
dormant into `main`.

## Feasibility outcome

The frozen unseen-router check used eight cases, each run twice, with no retries
or prompt changes. All 16 outputs were structurally valid and ended with
`finish_reason=stop`; lane selection was stable across all eight repeated cases.
The ordinary source-only cases selected the source lane with nonempty retrieval
questions. However, both repetitions of one previously unseen Spanish mixed
source-plus-transformation request selected the conversation-only lane. This
violated the predeclared asymmetric grounding safety boundary.

The configured model demonstrated useful transcript-only transformation
feasibility when the operation was known and fixed, including the bounded M1E
examples. It did not reliably determine whether a natural-language request
could safely bypass source grounding. This is a product feasibility NO-GO for
learned free-text routing, not a failure of the bounded executor experiment.

## Actions and limits

- The router experiment is complete; no router p2, prompt tuning, regex guard,
  confidence threshold, or expanded router corpus is authorized by this
  closeout.
- The canonical API M2 smoke was not run.
- The natural-language lane was not activated and the 01B candidate was not
  promoted to `main`.
- Private raw request/response observations remain outside Git under
  `/tmp/beta_conv_01b_feasibility/raw/ir002_unseen`; the sanitized result is
  recorded in the preserved 01B feature branch's
  `docs/evidence/beta_conv_01b/FEASIBILITY_RESULT.md`.

## Successor

BETA-CONV-01C uses explicit, application-owned conversation actions while
preserving the existing deterministic grounded free-text path. It does not
reuse the 01B natural-language router or copy the 01B production implementation
into `main`.
