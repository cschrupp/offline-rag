# Slice 18B Workstation Qualification Status

**Implementation status:** Revision 2 candidate `ab1c11c57118668dd6ac44beb0a69e4ef5f5f522` built and recorded.
**18B-R Docker runtime cell:** PASS — exact-candidate image, CPU runtime, API/UI readiness, local retrieval/reranking, synthetic ingestion, grounded citation provenance, and a successful query after container replacement with `/data` preserved were verified using local Windows Ollama.
**18B-P workstation package cell:** PASS — release archive built from the exact candidate, external and internal hashes verified, package contents audited, and focused installer/package tests passed.
**Slice 18B:** READY FOR INDEPENDENT REVIEW; Human acceptance and promotion have not occurred.
**SYSTEMD_USER_RUNTIME:** `DEFERRED_REAL_HOST_VALIDATION`
**WSL_DISTRO_LIFECYCLE:** `DEFERRED_REAL_HOST_VALIDATION`
**Native Windows spike:** Separate branch; not part of this qualification.

The implementation host is a sandboxed WSL2 environment reporting x86-64 and a
`microsoft-standard-WSL2` kernel. The `systemctl --user show-environment` probe
returned `Failed to connect to bus: Operation not permitted` inside the
sandbox. Dynamic systemd-user lifecycle qualification is therefore deferred.
Revision 2 uses Docker for reproducible runtime qualification and a built
release archive for workstation package qualification; neither is represented
as clean physical Linux/WSL host testing.

Qualification evidence belongs under this directory. It must be sanitized and
must not contain user corpus or model bytes, secrets, prompts, source
names/content, or unsanitized host logs.

See `REV2_IMPLEMENTATION.md`, `PACKAGE_RESULT.md`, `PACKAGE_MANIFEST.json`,
and `DOCKER_QUALIFICATION.md` for the candidate, package identity, validation,
and the exact runtime limitation. This status is not a Slice 18B acceptance or
promotion record.

The workstation service is expected to outlive its launching shell only while
the Linux environment remains running; systemd user-manager lingering is a
preflight requirement. On WSL, the distribution may still stop under Windows/WSL
lifecycle policy. A later real-host check must separately verify shell
independence while the distro runs and persistent-state/service recovery after
the distro is reopened or restarted. The service is not required to keep WSL
alive.
