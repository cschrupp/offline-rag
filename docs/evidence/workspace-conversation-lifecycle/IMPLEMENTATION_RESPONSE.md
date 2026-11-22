# Lifecycle design checkpoint

The unchanged workspace conversation route was exercised over real loopback
HTTP with Uvicorn. The test used temporary workspace state, existing synthetic
workspace fixtures, and fake embedding, reranker and provider resources at
the supported factory seams. No application handler or lifecycle hook was
replaced. The test made six conversation requests.

- Normal turn returned HTTP 200 with an answer and citations.
- At configured query capacity one, both competing requests entered the
  held scorer, then returned 200 after release.
- Closing a client socket during held reranking did not stop backend work.
  A second request reached the scorer before the abandoned worker returned.
  Both ultimately persisted answered conversation traces.
- Under SIGTERM, with the scorer released within the bounded Uvicorn grace
  period, the active response completed and lifespan closed the scorer
  afterward. The process returned the SIGTERM exit status. All six
  conversation traces linked distinct query trace IDs. Registry active
  count was zero at all five held scorer entries. This test did not cross
  grace expiry and does not establish safety after grace expiry.
- Server-side deadline enforcement is absent on this route. No deadline
  case was counted as passing.

[Baseline output](BASELINE.txt) · [Lifecycle design and next authority](DESIGN.md)

Run from the repository root with its provisioned Python development
environment and local tiktoken artifacts.

```bash
PYTHONPATH=src timeout -k 3 65 python \
  docs/evidence/workspace-conversation-lifecycle/baseline.py \
  /absolute/path/to/models/tokenizers/tiktoken
```

Ruff lint and format, Python compilation and Git whitespace checks passed.
The run emitted the existing Starlette TestClient import deprecation
warning from the shared test fixture. The transport test itself used real
HTTP sockets.

The proposed corrective preserves validation and immutable snapshot
binding, then uses shared query admission and an owned worker with
disconnect, cooperative deadline and shutdown tracking. The design
specifies capacity, trace commit semantics, regression fixtures, and the
separate authorization required for Stage 2. Neither the corrective nor
Stage 2 was executed. No VM work, production changes, activation or merge.
