# 18D-R Docling native runtime corrective

- Starting branch head and base: d0250895df86a98fd1d206ac45fc99c338ae4cd0.
- Dockerfile commit: fb2a129165e24e943301569c2f2397b1ed43f6f2 (direct child of the base).
- Technical candidate: c5a973955f20ea29abe473ffe9ae816946eb26ad (parent fb2a129165e24e943301569c2f2397b1ed43f6f2).
- Technical paths: `deploy/Dockerfile`, `scripts/verify_docling_runtime.py`.
- Evidence paths: this directory only.

The runtime stage installs the seven Debian 13 native packages implicated
by the observed OpenCV linkage failures. The existing CPU/CUDA selection,
runtime commands, user, mounts, Python lock, and parser policy are preserved.

The release runbook requires the standalone verifier before cutover.
It complements the Slice 16H HTTP smoke and can run without models in
ordinary release packaging. Model-provisioned environments can pass the
optional PDF arguments to exercise the canonical parser without network access.

## Checks

- `git diff --check`, targeted Ruff lint and formatting, Python compilation
  (including embedded container code), and runbook `bash -n`: PASS.
- `pytest -q tests/unit/test_docling_artifacts.py tests/unit/test_docling_parser_identity.py`:
  6 passed using the existing local dependency environment.
- Prior image negative control: `python scripts/verify_docling_runtime.py
  seneca-review:872419079b2a 872419079b2a709522eb9bf8a2dcc5f03bb815b3`
  exited nonzero at `cv2.abi3.so` with `libxcb.so.1 => not found`.
  A separate scan of the prior wheel's shared objects found all eight missing
  libraries listed in the authorization. The seven package names resolve
  both GLib libraries through the same Debian package.
- UI suites were not rerun because this corrective only changes container
  packaging and its qualification script. The inherited outdated Engineering
  heading assertion remains documented in the UUID corrective evidence.

## Exact CPU image build

```bash
sha=c5a973955f20ea29abe473ffe9ae816946eb26ad
docker build -f deploy/Dockerfile --build-arg SENECA_DEPENDENCY_PROFILE=cpu-release --build-arg SENECA_SOURCE_SHA="$sha" -t "seneca-review:${sha:0:12}" .
```

The first build attempt failed in locked dependency installation. The exact
candidate retry completed and the final image was inspected locally.

| Check | Result |
| --- | --- |
| Image ID and local repo digest | `sha256:44df9cab79f24e58ef1027f69050dc7473bd30c8ada1c45ed86f08350f82511e` |
| Image size | 2,635,989,176 bytes |
| Revision label | `c5a973955f20ea29abe473ffe9ae816946eb26ad` |
| Dependency profile | `cpu-release` |
| Image contract and runtime UID/GID | PASS, 10001:10001 |
| Common secret/private file paths and secret-like image environment | PASS within verifier's explicit checks |
| OpenCV linkage | PASS, 42 shared objects |
| OpenCV and TableFormer imports | PASS, OpenCV 5.0.0 and TFPredictor |
| Real PDF smoke | PASS, artifact readiness and canonical conversion, 2 useful blocks |

The native verifier ran with `python scripts/verify_docling_runtime.py
seneca-review:c5a973955f20 c5a973955f20ea29abe473ffe9ae816946eb26ad`.
The same verifier was run with `--models` pointing to a readable copy of
the existing local Docling tree and `--pdf tests/fixtures/ingestion/pdf/born_digital_reference.pdf`.
Both runs used the installed final image and `--network none`. The fixture
and model copy were mounted read-only, and the original model tree was
untouched. The processor emitted a slow-image-processor advisory.
The VM deployment and its product smoke remain operator steps after review.
