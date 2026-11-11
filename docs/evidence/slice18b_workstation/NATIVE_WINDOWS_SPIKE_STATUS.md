# Slice 18B Native Windows Portability Spike

**Spike branch:** `spike/slice18b-native-windows-portability`
**Base:** `8431c134d2f85e74afe80febd0ca75ac451f65f1`

## Scope implemented for review

- Added a project-owned file-lock adapter. POSIX keeps `fcntl.flock`; the
  Windows path uses standard-library `msvcrt` byte-range locks on persistent
  lock files.
- The Windows blocking path retries live-lock contention without a timeout;
  nonblocking contention maps to `BlockingIOError`, which the existing lease
  classes map to their existing application errors.
- Corpus, workspace, and Gold Lab lease call sites use the shared adapter.
  Existing resource acquisition order and lock-file names are unchanged.
- POSIX-only `resource` imports are now local to their best-effort measurement
  functions. When unavailable, the existing measurement fields remain null or
  explicitly unavailable.

## Evidence available from this host

The implementation host is Linux under WSL2, not native Windows. Therefore
native W0–W3 have **not** been run and no authorized native-Windows feasibility
disposition can be determined from this evidence.

On the available Linux host:

- focused cross-process lock tests pass for live-owner exclusion, process-death
  release, blocking wait/release, and persistent lock-file reuse;
- mocked adapter tests pass for Windows lock-violation retry and nonblocking
  error normalization;
- existing corpus, workspace, and Gold Lab lease regressions pass;
- unavailable `resource` imports preserve null/unavailable diagnostic fields.

These tests are implementation evidence only. They do not qualify native
Windows imports, doctor, runtime construction, or actual Windows lock semantics.
Run W0–W3 on native Windows before making any portability claim. No native
Windows installer or service is included.
