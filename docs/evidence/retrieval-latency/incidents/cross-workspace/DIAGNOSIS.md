# Seneca incident diagnosis — 2026-11-21 UTC

**Classification: slow retrieval/context execution. The immediate cause of
the intermittent client disconnects remains inconclusive.** The exact question
completed three times on the server. Retrieval/assembly consumed 92.7–96.6%
of grounded execution. Every attempt reached OpenRouter and returned an
answered terminal trace with citations. One has an HTTP 200 access entry.
The other two have server completions but no matching access entry.

| Admission UTC | Context (s) | Generation (s) | Grounded total (s) | Trace committed UTC | HTTP |
|---|---:|---:|---:|---|---|
| 19:01:45.266 | 102.401 | 3.553 | 105.954 | 19:03:31.725 | No entry found |
| 19:02:41.938 | 77.453 | 6.015 | 83.468 | 19:04:05.423 | No entry found |
| 19:03:42.401 | 39.037 | 3.067 | 42.104 | 19:04:24.513 | 200 at 19:04:24.526 |

The 200 correlates by workspace and timestamp, 13 ms after conversation
trace commit. The 42.12 s admission-to-access interval omits client
transport and any pre-admission queue. There are no client close timestamps
or matching HTTP error statuses for the longer attempts. The roughly 57 and
60 second resubmission intervals are not measured timeout durations. No
60/90/120 second timeout could be verified.

Rich's title, source display name and 59,777-byte source metadata matched.
Workspace revision 2, snapshot
`snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`
contains ten indexed child passages, all from the one active source.
Traces use all-active mode with one document. The grounded assembler invokes
hybrid+BGE on a nonempty pool, capped at 30. The observed workload is therefore
at most ten pairs, expected as a single batch if fusion returned all ten.
The durable records do not retain actual candidate count, BGE stage time,
query-specific CPU or model-load elapsed time. The first observed exact turn
after restoration may have paid lazy model load or cache costs, but the data
cannot distinguish warm-up from other effects. The first two exact turns
overlapped about 50 s; the second and third overlapped about 23 s. This makes
CPU contention plausible. An earlier same-workspace cluster had up to four
overlapping traced admissions. That cluster included a different question
that ended in response_parse_error after 121.0 s context and 8.3 s generation;
it is not an exact-question failure.

Recipes remains a separate 603-passage snapshot. Its ten earlier selected
French-fries cases spent 80.2–126.1 s assembling context and 0.6–3.9 s in
generation, then recorded model_abstain. An abstention is a terminal model
result and does not imply provider unavailability. The 30-pair BGE dominance
measured on that workload cannot be assigned to Rich's ten-passage workload
without stage timing.

Host port 80 is Docker's port publisher for the single Uvicorn worker on
8080. No HTTP reverse proxy or project forwarding rules were found. Deployed
Uvicorn 0.54.0 has a 5 s idle keep-alive default, not an in-flight response
deadline. Browser fetch has no explicit deadline at this call site and
TanStack retry is false. Client-network or unmanaged intermediary behavior
remains unknown. The workspace turn is synchronous and supplies no operation
handle. It therefore does not use the admission and disconnect watcher used
on /v1/query. The installed h11 send implementation returns immediately
when already disconnected, before access logging. Completion without an
access entry is consistent with abandoned HTTP connections and continued
backend work. The actual socket-close time and cause are unavailable, so no
specific post-close execution duration is established.

The active generation configuration was enabled, OpenAI-compatible,
openrouter.ai/api/v1, model ~deepseek/deepseek-flash-latest, 120 s provider
timeout, credential-present true, and strict-offline false. Endpoint and
model were approved. Pending settings were absent. One existing
non-generative /models probe passed and listed the selected model. The
generation fingerprint matched the three current traces and earlier
pre-restart traces. The 120 s budget is for provider I/O and does not
govern the whole conversation POST.

The same image and container were running. Both health endpoints returned
200, Docker auto-restart count was zero, and there was no OOM indication.
At inspection CPU was 0.2%, container memory usage 2.81 GiB, host available RAM
12,618 MiB and swap used 6 MiB. Durable managed operations were terminal.
These are current snapshots, not peak incident measurements. Cloud audit
and system history showed stop/start around 18:40–18:41 UTC. The planned
batching diagnostic then stopped the service at 18:44:46 and restored
readiness at 18:54:29. All three exact attempts began after restoration.
The 7,200 s STOP policy remains enabled. No STOP or container restart
overlapped those three attempts.

**Smallest justified next action.** With separate approval, submit exactly
one browser turn on revision 2 for the same question, no prior turns and
the same all-active one-document scope. Wait for idle and healthy service.
Capture client UTC request start, first response byte, status or network
error and close time. Correlate with timestamped server access logs, socket
close observation (metadata only), and trace write times. If finer
retrieval timing is needed, use a separately reviewed diagnostic that
projects existing dense/rerank timings and candidate count without changing
the executor or science. Capture CPU samples during the one request.
No repeated submission, payload logging, or production timeout change.

If the controlled trace confirms abandoned work and overlapping-load
amplification, the smallest server corrective candidate is to reuse the
existing owned query-worker admission and disconnect signaling on the
workspace route. Retain capacity until the worker exits. Cancellation is
cooperative and will not interrupt an in-progress Torch forward call.
Validate bounded admission, disconnect before generation where a checkpoint
permits it, uninterrupted cited responses, immutable snapshot binding,
and trace compatibility. Roll back by restoring the previous image with
the same mounts and settings, then verifying health and publication state.
If the isolated query remains slow, time the existing stages before choosing
a separate latency corrective. No proxy, provider or batching change is
supported as an incident workaround on the available evidence.

No conversation query, inference campaign, restart, deployment, configuration
edit, or workspace mutation was performed in this investigation.

## Deployed code references

- Workspace conversation route: src/offline_rag/api/workspaces.py:675–690.
- Conversation trace admission and completion: src/offline_rag/app/conversation/turn.py:131–150,210–254.
- Managed reference route: src/offline_rag/api/query.py:47–90 and src/offline_rag/api/workers.py:25–67.
- Bound query and trace timing: src/offline_rag/app/query.py:319–336,423–455.
- Candidate and scorer boundary: src/offline_rag/rerank/retrieve.py:132–166,221–240.
- Browser behavior: ui/src/pages/WorkspacePage.tsx:821–829 and ui/src/api/client.ts:96–105,419–444.
