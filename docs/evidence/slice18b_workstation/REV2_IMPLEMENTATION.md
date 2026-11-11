# Slice 18B Revision 2 — Implementation and Validation

- **Authority:** `S18B-WORKSTATION-DISTRIBUTION-REV2-001`
- **Accepted foundation:** `b546e5ad44a7f40fcef1baafd8bfcf9828ad8050`
- **Canonical base:** `8431c134d2f85e74afe80febd0ca75ac451f65f1`
- **Candidate:** `ab1c11c57118668dd6ac44beb0a69e4ef5f5f522`
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

- Workstation tests: **21 passed**.
- Ruff check and format check for changed Python files: **passed**.
- Shell syntax (`build_package.sh`, `install.sh`, `provision.sh`): **passed**.
- UI tests: **49 files / 459 tests passed**.
- UI lint and typecheck: **passed**.
- UI production build: **passed**; Vite reports its existing large-chunk advisory.
- `git diff --check`: **passed**.
- Dockerfile build check: **passed**.
- Exact-candidate Docker image build: **passed**.

The UI test suite took 167.68 seconds in this run. Duplicate TanStack Query
observer warnings appeared in the existing Slice 16G-I3 tests; the suite
completed successfully.

## Qualification boundaries

This environment is sandboxed WSL2, not a clean Ubuntu or Windows/WSL
qualification host. Dynamic systemd-user lifecycle and WSL distro lifecycle
remain deferred to real-host validation. The local Ollama service was not
available during the product query attempt; the request failed safely with
`generation_unavailable`. Therefore, the complete grounded answer/citation
path and query-after-container-replacement acceptance criteria remain open.

No real-host systemd/WSL claim, successful grounded-query claim, or overall
18B-R PASS is made here. Promotion is not authorized by this record.
