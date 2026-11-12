# Slice 18B Revision 2 — Implementation and Validation

- **Authority:** `S18B-WORKSTATION-DISTRIBUTION-REV2-001`
- **Accepted foundation:** `b546e5ad44a7f40fcef1baafd8bfcf9828ad8050`
- **Canonical base:** `8431c134d2f85e74afe80febd0ca75ac451f65f1`
- **Initial implementation:** `ab1c11c57118668dd6ac44beb0a69e4ef5f5f522`
- **Integrity corrective candidate:** `7cc743a276587db45c971d035967a0f3b1133799`
- **Branch:** `feature/slice18b-workstation-distribution`

## Result

Revision 2 adds a release-builder workflow that packages the exact committed
source revision and compiled production UI. The end-user installer consumes
the extracted package, verifies its internal checksum manifest and release
identity before installation-state mutation, and no longer requires Git,
Node.js, npm, or a repository checkout. Installed release metadata is derived
from the validated `RELEASE.json` package provenance.

The existing versioned release, final-path virtual environment, non-editable
installation, stable symlink activation, rollback, persistent data/model
separation, strict-offline configuration, and local service mechanics are
retained. No production application module, Dockerfile, dependency metadata,
retrieval behavior, embedding contract, or scientific configuration changed.

## Validation

- Initial workstation tests: **21 passed**.
- Integrity corrective workstation tests: **25 passed**, including changed,
  missing, extra-file and symlink cases.
- Ruff check and format check for changed Python files: **passed**.
- Shell syntax (`build_package.sh`, `install.sh`, `provision.sh`): **passed**.
- UI tests: **49 files / 459 tests passed**.
- UI lint and typecheck: **passed**.
- UI production build: **passed**; Vite reports its existing large-chunk advisory.
- `git diff --check`: **passed**.
- Dockerfile build check: **passed**.
- Exact-candidate Docker image build: **passed**.

The integrity corrective changes only the workstation installer and its test
file. It changes no Docker inputs, application source, dependency metadata or
runtime policy; the independently reviewed 18B-R evidence remains applicable
without a Docker rerun.

The UI test suite took 167.68 seconds in this run. Duplicate TanStack Query
observer warnings appeared in the existing Slice 16G-I3 tests; the suite
completed successfully.

## Qualification boundaries

This environment is sandboxed WSL2, not a clean Ubuntu or Windows/WSL
qualification host. Dynamic systemd-user lifecycle and WSL distro lifecycle
remain deferred to real-host validation. An initial query attempt made before
the Windows Ollama service was available failed safely with
`generation_unavailable`; after the user reported Ollama was available, the
bounded local product smoke completed successfully as recorded in
`DOCKER_QUALIFICATION.md`.

No real-host systemd/WSL claim is made here. This evidence does not authorize
promotion; the candidate remains for independent review.
