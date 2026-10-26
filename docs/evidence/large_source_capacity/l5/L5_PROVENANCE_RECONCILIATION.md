# L5 provenance reconciliation

This evidence-only record resolves the provenance labels used by the L5
campaign artifacts. It does not change any raw cell JSON, preflight result,
partial log, fixture identity, measurement, or campaign disposition.

## Commit roles

The relevant subjects have distinct roles:

| Subject | Role |
|---|---|
| `32107a1b5c96b1435e50a23ca61078e9d6939af4` | Original L5 campaign-definition freeze. This commit created the normative freeze document and fixture manifest, including the progressive cell order, gates, limits, and scope lock. |
| `70cea558bd0e8f35fb23057b9ee2c1a4ab89a450` | Pinned execution baseline. This follow-up commit records `32107a1...` as the freeze-definition subject and is the exact tracked subject used by every successful L5 cell and the CPU preflight (`git_sha` / `exact_git_sha`). |
| `70f01642eeb832e9ecf19598635f93ddf70a9e3b` | Evidence-publication candidate. It added the raw Q25, Q100, Q100-CONFIRM, Q250 partial logs, preflights, duplicate check, campaign summary, and assessment over the pinned execution baseline. |
| `5e36f34b9ccd6daea837d78daf0de59b5fdeff18` | Evidence-index publication. It added `L5_EVIDENCE_INDEX.md` only; it did not alter execution or measurement evidence. |

Accordingly, the freeze document's `Campaign freeze subject` field names
the original freeze-definition subject (`32107a1...`), while the campaign
summary, assessment, ROADMAP entry, and evidence index use that label for the
operational execution baseline (`70cea55...`). This is a historical naming
difference, not two different execution subjects. The raw execution identity
is unambiguous: all successful cells and the CPU preflight record
`70cea558bd0e8f35fb23057b9ee2c1a4ab89a450`.

## Authority roles

The raw cell and CPU-preflight top-level field
`authority = S16-K-LARGE-SOURCE-CAPACITY-L4-INSTRUMENTATION-HARNESS-IMPLEMENTATION-AUTH-001`
is the implementation provenance of the L4 qualification harness. It is
paired with `authority_mode = qualification` and the exact execution subject
`70cea55...`; it is not the campaign authorization.

The campaign authorization is:

`S16-K-LARGE-SOURCE-CAPACITY-L5-PDF-QUALIFICATION-EXECUTION-AUTH-001`

That L5 execution authority is recorded in the freeze document, campaign
summary, and assessment. It governs the Q25/Q100/Q250/Q512 campaign and binds
the raw cell records to the L4 harness implementation authority. No raw cell
JSON is rewritten because its existing authority field accurately preserves
the harness provenance.

## Measurement interpretation carried into L6

The parser-stage RSS values reported in the assessment (approximately
6.59–6.60 GiB for Q100 and Q100-CONFIRM) are parser-phase sampled peaks.
They are not the whole-process memory envelope. The raw records also report
whole-window RSS peaks of 15,223,230,464 bytes for Q100 and
15,510,642,688 bytes for Q100-CONFIRM; L6 must use the exact whole-window
values from the raw JSON
alongside parser-stage RSS and must not treat 6.6 GiB as total process memory.

The campaign result remains unchanged:

```yaml
campaign_terminal: PROFILE_PARTIAL_QUALIFICATION
cpu_q25: VALID_PASS
cpu_q100: VALID_PASS
cpu_q100_confirm: VALID_PASS
cpu_largest_confirmed_class: Q100
q250: INVALID_EVIDENCE / HOST_TERMINATED
q512: NOT RUN — progressive stop
cuda: PROFILE_NOT_EVALUABLE
production_limits: UNCHANGED
l6: NOT AUTHORIZED
```
