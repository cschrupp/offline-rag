# L5 evidence index

Campaign definition freeze subject: `32107a1b5c96b1435e50a23ca61078e9d6939af4`

Execution baseline subject: `70cea558bd0e8f35fb23057b9ee2c1a4ab89a450`

Evidence candidate before the provenance reconciliation: `70f01642eeb832e9ecf19598635f93ddf70a9e3b`

Previous evidence-index subject: `5e36f34b9ccd6daea837d78daf0de59b5fdeff18`

All files below are evidence-only artifacts. The large PDF fixtures are not committed.

| Artifact | SHA-256 | Size |
|---|---|---:|
| [`L5_CAMPAIGN_FREEZE.md`](L5_CAMPAIGN_FREEZE.md) | `36d8e7187736f5515ccff653202578c01d2ed864d3b9e236338e69a0692c667d` | 2467 bytes |
| [`L5_PROVENANCE_RECONCILIATION.md`](L5_PROVENANCE_RECONCILIATION.md) | `a4b25d00127a291afe2a1bcd10117e980ac5ae7d81cf4c75c44f07333ee6635a` | 3395 bytes |
| [`l5_campaign_summary.json`](l5_campaign_summary.json) | `e89ce543152b43aaefdde9a0630808730409679fdf30718a4ee7ccd396c55292` | 14251 bytes |
| [`L5_QUALIFICATION_ASSESSMENT.md`](L5_QUALIFICATION_ASSESSMENT.md) | `6bfc40aa75ade74984eb9a80f3b987eeebfbd4ce4c9ce0340f4886928cc356ae` | 3454 bytes |
| [`l5_fixture_manifest.json`](l5_fixture_manifest.json) | `d9e76aacd212c0eb0dc7b262ba4e5cdd5ccd33829cfbe3afe8ba64c09a48e0b6` | 2511 bytes |
| [`cells/cpu_onnx_fp32_v1_Q25.json`](cells/cpu_onnx_fp32_v1_Q25.json) | `e49b593b441255d740f1bad0cbe7342e12f12473c56a6dbb690ed4f25ceaa377` | 3147078 bytes |
| [`cells/cpu_onnx_fp32_v1_Q100.json`](cells/cpu_onnx_fp32_v1_Q100.json) | `b739c1f58076162ba43373839a52a749ca855e70e1cc565ed191c2447d318e43` | 5357274 bytes |
| [`cells/cpu_onnx_fp32_v1_Q100_CONFIRM.json`](cells/cpu_onnx_fp32_v1_Q100_CONFIRM.json) | `40720ce72d5e803f2ee241afacaf1e026612eb0a5ac45c470e7d88040ef11b0e` | 6045942 bytes |
| [`duplicate_identity_check.json`](duplicate_identity_check.json) | `d9f7e3afcca0f0ffb0f4d491d1113a1736e1a9ea1341e66214f8152fbdfb7bdf` | 4528 bytes |
| [`partial_q250/cpu_onnx_fp32_v1_Q250.stdout.log`](partial_q250/cpu_onnx_fp32_v1_Q250.stdout.log) | `905498f20c67311ca4f9dfa98a0a137a228bc91db25247a7f6c1fa890f98372c` | 91670 bytes |
| [`partial_q250/cpu_onnx_fp32_v1_Q250.stderr.log`](partial_q250/cpu_onnx_fp32_v1_Q250.stderr.log) | `6fae064f68e0947cab3d971a27275c4d320dea508dc3a85976fef8b199b69bba` | 949 bytes |
| [`preflight/cpu_onnx_fp32_v1.json`](preflight/cpu_onnx_fp32_v1.json) | `9da770587b1d6442d450a9a22a073cb5390755ed7e2b839c6796e4fa8309788f` | 239965 bytes |
| [`preflight/cuda_fp16_v1.json`](preflight/cuda_fp16_v1.json) | `048fa5b6f2501f1475d453fb9f3d283e458d477c2d0bb8333a6fb265c240af1b` | 246 bytes |

The provenance reconciliation explains the distinction between the freeze-definition subject and the pinned execution baseline, and binds the L4 harness implementation authority to the L5 execution authority.

The evidence JSONs contain identity, provenance, measurements, and managed-operation state; they do not contain PDF source contents.
