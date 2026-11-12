# Slice 18B Workstation Qualification Status

**Slice status:** COMPLETE / HUMAN ACCEPTED / PROMOTED.
**Accepted technical candidate:** `7cc743a276587db45c971d035967a0f3b1133799`.
**Accepted evidence head promoted to main:** `f5eda171925b791f94589637eb690a0de125aefb`.
**18B-R Docker runtime cell:** PASS — the reviewed `ab1c11c5` image passed CPU runtime, API/UI readiness, local retrieval/reranking, synthetic ingestion, citation provenance, and post-replacement query checks. The `7cc743a2` correction changes only the workstation installer and tests, not Docker inputs or application runtime.
**18B-P workstation package cell:** PASS — exact file-set closure is enforced before content hashing; release archive built from the corrective candidate, external and internal hashes verified, package contents audited, and focused installer/package tests passed.
**Slice 18B:** COMPLETE / HUMAN ACCEPTED / PROMOTED.
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
and the qualification details. The deferred real-host checks remain open
follow-up validation; they were not performed or implicitly qualified by
promotion.

The workstation service is expected to outlive its launching shell only while
the Linux environment remains running; systemd user-manager lingering is a
preflight requirement. On WSL, the distribution may still stop under Windows/WSL
lifecycle policy. A later real-host check must separately verify shell
independence while the distro runs and persistent-state/service recovery after
the distro is reopened or restarted. The service is not required to keep WSL
alive.
