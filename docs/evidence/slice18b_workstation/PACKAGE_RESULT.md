# Slice 18B Revision 2 — Workstation Package Result

## Artifact identity

- Source SHA: `ab1c11c57118668dd6ac44beb0a69e4ef5f5f522`
- Version: `0.1.0`
- Target: `linux-x86_64`
- Python: `3.14`
- uv: `0.11.18`
- Dependency profile: `cpu-release`
- Artifact: `seneca-workstation-0.1.0-linux-x86_64-ab1c11c57118.tar.gz`
- Size: `2,491,359` bytes
- SHA-256: `6c28a62afe7173e7a44103d62b7295621c91327c552330026cd669b1c3227950`
- Payload files covered by internal `SHA256SUMS`: `494`

The archive and external `.sha256` file are generated under ignored
`dist/workstation/`; they are not committed.

## Checks

- External archive checksum: **PASS** (`sha256sum -c`).
- Extracted package internal checksums: **PASS** (494 files).
- Required installer, release metadata, lockfile, Python package, config,
  compiled UI and workstation/provisioning scripts: **present**.
- `.git`, `node_modules`, `.env`, virtualenv, user data, and provisioned model
  directories: **absent**.
- Package builder checks for a clean committed tree and uses the exact source
  SHA; `RELEASE.json` records matching source and UI source identities.
- Automated package tests exercise tampered-payload rejection before
  installation-root mutation, operation outside a Git worktree, installed
  provenance, and no Git/Node/npm requirement for end-user installation.

## Disposition

**18B-P: PASS** for the Linux x86-64 package-builder, archive-integrity, and
installer-contract scope in this sandbox. Real-host systemd and WSL lifecycle
checks remain separately deferred.
