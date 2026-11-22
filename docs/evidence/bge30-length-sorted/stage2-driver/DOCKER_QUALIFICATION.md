# Docker transport preparation

**Execution gate remains closed.** This revision adds the Docker/HTTP
transport for load requests, a single-send socket client, and an
independent supervisor primitive. It leaves the integrated source and
diagnostic image unchanged. The adapter accepts only the pinned image
and network-disabled session, and cleanup targets the exact session
label and name. Reports require a socket-send marker and a matching
server terminal record. Accepted records also require a slot-release
attestation. Lifecycle requests explicitly fail closed because the
route-specific control and server event producer are still missing.

The isolated transport smoke used the pinned local image with a
disposable HTTP fixture in its loopback namespace. It used the
workspace turn URL shape. The fixture was a small synthetic HTTP
server, so this run does not qualify the actual Seneca route. A real
socket send correlated to an injected rejection, a second send with
missing terminal evidence failed closed, and bounded Docker stop
removed a server that ignored SIGTERM. The scratch fixture mounted
no Qdrant backing. The test therefore establishes container cleanup
only. The standalone supervisor provides bounded termination and
restoration callbacks; driver-crash survival and disposable service
restoration have yet to be rehearsed with it.

Run the smoke from the repository root using the existing Python
environment and retained image:

```bash
timeout -k 5 45 python \
  docs/evidence/bge30-length-sorted/stage2-driver/rehearse_transport.py
```

[Transport observations](TRANSPORT_RESULTS.txt) and
[authorization](DOCKER_AUTHORIZATION.md) are retained. Before final
qualification, connect valid server-side operation and trace events
to this transport, implement all four lifecycle cases, and rehearse
the full 36-case Docker schedule and independent restoration including
forced launcher termination and failed restoration. The sanitized
effective settings comparison and positive host preflight are also
pending. No host inspection, native workload, VM maintenance,
production change or merge occurred. No final VM execution authority
is recommended for this revision.
