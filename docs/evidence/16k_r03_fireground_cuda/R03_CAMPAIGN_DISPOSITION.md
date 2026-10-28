# S16K-R03 Fireground CUDA Current-Main Disposition

**Authority:** `S16K-R03-FIREGROUND-CUDA-CURRENT-MAIN-DISPOSITION-AUTH-001`
**Authorized base:** `b7997115b1e14ee840f2abda5bac6ced9e758e3b`
**Branch:** `diagnostic/16k-r03-fireground-current-main-disposition`
**Exact fixture:** `Fireground_Operational_Guides.pdf`, 6,796,067 bytes, SHA-256 `01bea4d628ffea01aab164535c81392a8b42b9a587f9b6295f302a9938f2f0c2`

## Result

**S16K-R03: NOT_REPRODUCED**

The historical Fireground CUDA/cublasGemmEx failure did not reproduce in five valid current-main, generate-heavy ingestions. The historical workspace-query HTTP-500 class also did not reproduce in the same-process grounded query. This is a bounded non-reproduction result; the original root cause is **not established**, and this report does not claim that the historical defect was identified or fixed.

## Runtime and isolation

The runtime preflight resolved the normal `auto` configuration to `cuda_fp16_v1` on CUDA. The observed lane was FP16, batch size 32, 1,024-dimensional embeddings, with SDPA. The exact runtime, model, host and capability values are recorded in [r03_campaign_evidence.json](r03_campaign_evidence.json).

Each cell used its own isolated data root and a fresh API process. Model files were reused read-only. The exact Fireground identity was absent from each populated baseline before its cell. No normal user corpus, model files, or cache was modified; no internet access was used.

For R03-B and C1–C3, the occupied baseline had 12 sources and 2,643 searchable children. Eleven historical source files were rebuilt using the current parser, yielding 2,043 children; a deterministic synthetic text corpus contributed 600 more. This matches the authorized 2.5k–3.2k workload range but is not an exact reconstruction of the historical corpus content. Fireground then raised the searchable total to 3,227. In each populated cell, 584 Fireground embeddings were generated, 2,643 existing embeddings were reused, and zero embeddings failed.

## Cell summary

| Cell | Validity | Generated / reused / failed | Children before → after | Result |
|---|---|---:|---:|---|
| R03-A | Valid | 584 / 0 / 0 | 0 → 584 | Published; CUDA active; API healthy |
| R03-B | Valid | 584 / 2,643 / 0 | 2,643 → 3,227 | Published; populated CUDA workload |
| R03-C1 | Valid | 584 / 2,643 / 0 | 2,643 → 3,227 | Published; same-process query answered with 2 citations |
| R03-C2 | Valid | 584 / 2,643 / 0 | 2,643 → 3,227 | Published |
| R03-C3 | Valid | 584 / 2,643 / 0 | 2,643 → 3,227 | Published |

Dense-generation times were 53,247 ms for A; 30,286 ms for B; and 68,938, 29,824, and 36,364 ms for C1, C2, and C3. The per-cell stage and total timings are in the JSON evidence.

R03-Q used the normal source-restricted conversation path in the same live API process after successful generation. It returned HTTP 200 and application status `answered`, with two citations; readiness remained HTTP 200 and the API process continued.

## Failure observations and limits

No counted operation reported embedding failures or a CUDA-class failure. The kernel ring buffer search found no OOM, killed-process, NVIDIA Xid, or CUDA-fault record. It did contain a `weston`/`libwayland-server` segfault entry; there is no evidence tying that compositor process to an R03 API process. The counted APIs all remained alive through ingestion and shut down cleanly afterward.

Two campaign-control attempts were excluded: an initial A monitor used the wrong namespace for observing the isolated API, and an initial C1 poller treated the transient `preparing` state as terminal. The A result was rerun under corrected monitoring. C1 was rerun from its pristine baseline after correcting the poller. These attempts are disclosed in the machine-readable evidence and do not count toward the five valid ingestions.

## Terminal

```yaml
S16K-R03: NOT_REPRODUCED
R03-A: VALID_PASS
R03-B: VALID_PASS
R03-C1: VALID_PASS
R03-C2: VALID_PASS
R03-C3: VALID_PASS
R03-Q: VALID_PASS
original_root_cause: NOT_ESTABLISHED
claim_historical_bug_identified_and_fixed: false
active_beta_blocker: NO, SUBJECT TO INDEPENDENT REVIEW / HUMAN ACCEPTANCE
production_code_changed: NO
product_policy_or_capacity_limits_changed: NO
promotion: NOT AUTHORIZED
```

No production code or product settings changed. No tests were needed because this candidate contains only campaign evidence and documentation. Stop for independent review; this result grants no Human acceptance, promotion, or downstream implementation authority.
