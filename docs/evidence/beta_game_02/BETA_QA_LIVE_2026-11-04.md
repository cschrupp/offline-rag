# Seneca — Live Beta QA Record (2026-11-04)

**Record status:** User-reported manual smoke evidence; registered for context,
not independently replayed.\
**Observed environment:** User's running Seneca installation; exact environment
configuration and GPU telemetry were not captured.\
**Canonical Git state reviewed:** `main` at
`4ea5c92a9082621f167e8fcd2a64d085534633f9`.

## Confirmed user observations

| Area | Observation | Evidence level |
| --- | --- | --- |
| Quick Play baseline generation | A new run advanced through proposal and evidence pooling and exposed playable Question Check content. | User-reported live observation; screenshots appeared in the conversation. |
| Gold evidence-pooling corrective | The `dense-model-query-prompt-v1` integration no longer prevented this run from producing an activity deck. | User-reported live outcome; not a full six-arm telemetry audit or scientific qualification. |
| Question Check | The user inspected a question and source text in the game and later reported Quick Play was working well. | User-reported live observation. |
| Workspace/source binding | A suspected cross-workspace source was checked and confirmed appropriate by the user. | User confirmation; no defect established. |
| Gold Lab Authoring settings | The user reported manually checking the Authoring settings and that they work well. | User-reported live observation; exact edit/save/restart sequence not captured. |

## Not verified by this record

- No independent replay, automated end-to-end smoke, server logs, or telemetry
  were collected for the live run.
- No claim is made that all six retrieval arms individually produced nonempty
  hits; the observation establishes reviewable pooled output only.
- Physical CUDA profile execution and GPU VRAM behavior remain unverified.
- Rapid Fire activation and mutation, end-of-session resume, replenishment, and
  durable judgment preservation after restart were not individually confirmed.
- Generation-settings edit/save/restart persistence was not explicitly
  confirmed. Authoring-settings persistence after restart was also not
  explicitly confirmed.
- The original failed Gold bootstrap operation remains historical evidence;
  this record does not revise or retry it.

## Disposition

**Live beta outcome:** Initial Quick Play and Question Check functional smoke:
**USER-OBSERVED PASS**. Gold Lab Authoring settings UI:
**USER-OBSERVED PASS**. Broad beta acceptance and full end-to-end testing remain
**OPEN**.

Record remaining checks in the beta QA queue without reopening already promoted
slices solely because coverage is incomplete. Do not infer acceptance or
promotion of an unexecuted slice.
