# Slice 18B Revision 2 — Workstation Package Result

## Artifact identity

- Source SHA: `7cc743a276587db45c971d035967a0f3b1133799`
- Version: `0.1.0`
- Target: `linux-x86_64`
- Python: `3.14`
- uv: `0.11.18`
- Dependency profile: `cpu-release`
- Artifact: `seneca-workstation-0.1.0-linux-x86_64-7cc743a27658.tar.gz`
- Size: `2,492,331` bytes
- SHA-256: `4beee79e359dfcd57996e3f58bf45145fcb094ee23e1fc295ba5c435723c3112`
- Files covered by internal `SHA256SUMS`: `493`

The archive and external `.sha256` file are generated under ignored
`dist/workstation/`; they are not committed.

## Checks

- External archive checksum: **PASS** (`sha256sum -c`).
- Extracted package internal checksums: **PASS** (493 files).
- Extracted file and directory set exactly matches the manifest; extra root
  entries, added payload files, missing entries, symlinks, and unsupported file
  objects are rejected before installation mutation.
- Required installer, release metadata, lockfile, Python package, config,
  compiled UI and workstation/provisioning scripts: **present**.
- `.git`, `node_modules`, `.env`, virtualenv, user data, and provisioned model
  directories: **absent**.
- Package builder checks for a clean committed tree and uses the exact source
  SHA; `RELEASE.json` records matching source and UI source identities.
- Automated package tests exercise tampered-payload rejection before
  installation-root mutation, operation outside a Git worktree, installed
  provenance, and no Git/Node/npm requirement for end-user installation.
- Integrity regressions: pristine package reaches host preflight; changed or
  missing listed files, added unlisted files, and added unlisted symlinks fail
  before installation roots are created.

## Disposition

**18B-P: PASS** for the Linux x86-64 package-builder, archive-integrity, and
installer-contract scope in this sandbox. Real-host systemd and WSL lifecycle
checks remain separately deferred.
