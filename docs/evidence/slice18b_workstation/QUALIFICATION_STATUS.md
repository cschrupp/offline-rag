# Slice 18B Workstation Qualification Status

**Implementation status:** Revision 2 in progress; not a qualification result.
**18B-R Docker runtime cell:** Not run.
**18B-P workstation package cell:** Not run.
**SYSTEMD_USER_RUNTIME:** `DEFERRED_REAL_HOST_VALIDATION`
**WSL_DISTRO_LIFECYCLE:** `DEFERRED_REAL_HOST_VALIDATION`
**Native Windows spike:** Separate branch and feasibility disposition pending.

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

The workstation service is expected to outlive its launching shell only while
the Linux environment remains running; systemd user-manager lingering is a
preflight requirement. On WSL, the distribution may still stop under Windows/WSL
lifecycle policy. A later real-host check must separately verify shell
independence while the distro runs and persistent-state/service recovery after
the distro is reopened or restarted. The service is not required to keep WSL
alive.
