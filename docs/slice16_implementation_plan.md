# Slice 16 — Implementation plan

```text
STATUS: ACCEPTED IMPLEMENTATION PLAN
DESIGN AUTHORITY: ACCEPTED / LOCKED
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
  docs/slice16_amendment_a1_seneca_product_ux.md
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7
  docs/slice16_amendment_a2_conversational_grounding.md
  A2 GOVERNANCE CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
16D-A: COMPLETE / ACCEPTED / SEALED
IMPLEMENTATION: 4f8962f2893ab433e6ea269ad54e46f67771ca70
LAST SEALED IMPLEMENTATION BASELINE:
  a952a75bc07191b213a5113eee53cb967fef8326
OBSERVED 16D-B1 CANDIDATE:
  6b6524001f063a628505f572e7ca13d954a38260
  PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
16D-B1 FOUNDATION REMEDIATION:
  ACCEPTED / SEALED
  ACCEPTED IMPLEMENTATION: c68cc3f8f16a2588ba093886f3e48e1c7037f83f
  VERIFIED CLOSEOUT: b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
  INDEPENDENT CLOSEOUT REVIEW: PASSED
16D-B2: COMPLETE / ACCEPTED / SEALED
  ACCEPTED IMPLEMENTATION: baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
  INDEPENDENT REVIEW: PASSED
  HUMAN ACCEPTANCE: ACCEPTED
  REWORK 1: COMPLETE
16D-B3: COMPLETE / ACCEPTED / SEALED
        ACCEPTED IMPLEMENTATION: 9c178ffb033cde41849379fc914f321697ff8691
        INDEPENDENT REVIEW: PASSED
        HUMAN ACCEPTANCE: ACCEPTED
        REWORK 1: COMPLETE
        REWORK 2: COMPLETE
        REWORK 3: COMPLETE
        REWORK 3A: COMPLETE
        AUTHORIZED BASELINE: 28aad06f89e6d00a0b81b51f9c2de38fed06cb22
        A3: ACCEPTED / LOCKED / SEALED
        A3 MATERIALIZATION: da1082d95630c12eaf0ce1a3b8d005aaa60d2f73
        EVIDENCE: docs/slice16d_b3_conversational_workspace.md
        A3 DOC: docs/slice16_amendment_a3_full_viewport_workspace.md
16D-C: COMPLETE / ACCEPTED / SEALED
        EVIDENCE: docs/slice16d_c_training_mode.md
AMENDMENT A4: ACCEPTED / LOCKED / SEALED
        A4 MATERIALIZATION: d12f6322ef13915002b49dcc8f1211052a66dcc5
        A4 DOC: docs/slice16_amendment_a4_workspace_portability_shell.md
16E: COMPLETE / ACCEPTED / SEALED
        ACCEPTED ENGINEERING IMPLEMENTATION: 3e1ce4c94fc511abb4e1d94bd194736d5497e64f
        WORKSPACE SOURCE-LOADING REMEDIATION: 9dd2b008ebf9feee279dc6d0e58fafb006288ee5
        REMEDIATION EVIDENCE TIP: 9cd5528ab6c6e22d2dca55aca221b65eac50269e
        EVIDENCE: docs/slice16e_engineering_evidence.md
        REMEDIATION: docs/workspace_source_loading_remediation.md
        CLOSEOUT: docs/slice16e_closeout.md
16F: COMPLETE / ACCEPTED / SEALED
     FINAL TIP: f25f8358aead7fcfe161fff388012cec23b5a573
     CLOSEOUT: docs/slice16f_closeout.md
16G-D0: ACCEPTED / FROZEN
  DESIGN TIP: 8af2dbab72d1a79f53b0f3958e7c7142b4273693
  DESIGN BLOB: edc2be739621dbedfc44ed77861119a35f8f6d18
  FROZEN DESIGN: docs/slice16g_gold_lab_games_pedagogy_design.md
16G-I1…I5: ACCEPTED
GAP-16G-01: ACCEPTED
GAP-16G-02:
  CLOSEOUT ACCEPTED
  IR-002 ACCEPT / HA-001 ACCEPTED
  HUMAN-ACCEPTED SUBJECT: e5d116b8a2990f3b0ac7f3fe1cbf052b4f6ac087
  ACCEPTED IMPLEMENTATION: 120c03cd79f3af142144a6b73e05bcb43fdacb76
  CLOSEOUT: docs/gap16g_02_gold_baseline_bootstrap_closeout.md
  MAIN PROMOTION: COMPLETE
  PROMOTED MAIN: f7fb999758ce6219be27d27a3f1c0a16ece97506
16G-I6: COMPLETE / ACCEPTED
  Independent review: 16G-I6-IR-002 — ACCEPT
  Human technical acceptance: ACCEPTED
  Exact accepted candidate: cc7ff520eb146fa555f2b48e1f7dcc89a7952729
16G: IMPLEMENTATION COMPLETE / ACCEPTED
16H: COMPLETE / ACCEPTED
  Independent review: 16H-IR-003 — ACCEPT
  Human acceptance: 16H-HA-001 — ACCEPTED
  Exact Human-accepted subject: 01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10
16I: COMPLETE / ACCEPTED
  Independent review: S16-I-MANAGED-OP-PROGRESS-IR-003 — ACCEPT
  Authority: S16-I-MANAGED-OP-PROGRESS-AUTH-001
  Exact accepted candidate: a3e65ce4bfa698f49e3aa21c4c5a7ddb0ea356a5
16J: PAUSED
  Seneca public-surface branding cleanup
16K: DESIGN ACCEPTED / FROZEN
  Design-open: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001 — AUTHORIZED
  Rework: S16-K-BETA-INGESTION-READINESS-DESIGN-REWORK-AUTH-001 — AUTHORIZED
    (addresses DESIGN-OPEN-IR-001 R1–R5)
  Human acceptance: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-001 — ACCEPTED
  HA record: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-AUTH-001 — AUTHORIZED
  HA-record IR: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-IR-001 — ACCEPT
  Exact Human-accepted design subject:
    0839b565cd60958141366048520236a71bf16fd0
  Design: docs/slice16k_beta_ingestion_readiness_design.md
  Detached managed-ingest lifetime ≠ HTTP request deadline; transport safety
    ≠ searchable workload (post-closeout; does NOT reopen Slice 16)
  Frozen order: 16K-A → 16K-B → baseline evidence → 16K-C → 16K-D
    → 16K-E → 16K-F → 16K-G
  16K-A: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
    Implementation authority:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-AUTH-001 — AUTHORIZED
    Independent review:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-IR-002 — ACCEPT
    Human acceptance:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-HA-001 — ACCEPTED
    HA record:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-AUTH-001 — AUTHORIZED
    Exact Human-accepted technical subject:
      1370b99327124045ad96005e829095683842c06f
    Branch: implementation/16k-a-managed-ingestion-correctness
    HA-record IR:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-IR-001 — ACCEPT
  16K-B: COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED /
    HA RECORD INDEPENDENTLY ACCEPTED
    Implementation authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-AUTH-001 — AUTHORIZED
    Exact implementation base:
      39e5e09363193b2315ada9e56cb3e1c14ba9377d
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-001 — REWORK REQUIRED (R1–R4)
    Rework authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-001 — AUTHORIZED
    Exact rework base:
      85f01f40080fe485b6ddb7700855aa34280c9c75
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-002 — REWORK REQUIRED (R3 / R4a / R4b)
    Rework authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-002 — AUTHORIZED
    Exact rework-002 base / parent:
      533a07c3d1313d08eae5647e4c266d4fa3a439c5
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-003 — REWORK REQUIRED (R3 orphan ownership)
    Rework authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-003 — AUTHORIZED
    Exact rework-003 base / parent:
      2c0e7bf21c8c427ee99b1b9518342a8080596463
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004 — ACCEPT
    IR-004 acceptance-record authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
    Exact independently accepted technical subject (IR-004 historical):
      91dba2e2885346ee595b920fd7dd02f671d2f7af
    Post-qualification remediation authority:
      S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-AUTH-001 — AUTHORIZED
    Exact post-qual remediation parent:
      037a39531abfd5f5335151a946dbede776c5f492
    Post-qualification chunk-ID collision IR:
      S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-IR-001 — ACCEPT
    Exact chunk-ID collision remediation subject:
      f4707b828a85dcc538fc1510a52ed416d7a89935
    Post-qualification lexical zero-term eligibility remediation authority:
      S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-AUTH-001
      — AUTHORIZED
    Exact lexical zero-term remediation parent:
      f4707b828a85dcc538fc1510a52ed416d7a89935
    Post-qualification lexical zero-term eligibility IR:
      S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001 — ACCEPT
    Exact independently accepted lexical zero-term remediation subject:
      349de6a55f0f362a42e646d946f0433cb33e6489
    Lexical zero-term IR-001 acceptance-record authority:
      S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001-ACCEPTANCE-RECORD-AUTH-001
      — AUTHORIZED
    Exact acceptance-record parent:
      349de6a55f0f362a42e646d946f0433cb33e6489
    Exact lexical zero-term IR-001 acceptance-record tip:
      fbc8bb17a51f800aaa8bcc030c163427d8dc1821
    Post-qualification dense-failure observability remediation authority:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
      — AUTHORIZED
    Exact dense-failure observability remediation parent:
      fbc8bb17a51f800aaa8bcc030c163427d8dc1821
    Post-qualification dense-failure observability IR:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-001
      — REWORK REQUIRED (R1)
    Exact dense-failure observability IR-001 subject:
      6f61f18441c2348faa81a1852196b7d300a1c4da
    Dense-failure observability rework authority:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001
      — AUTHORIZED
    Exact dense-failure observability rework parent:
      6f61f18441c2348faa81a1852196b7d300a1c4da
    Dense-failure observability rework IR:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002
      — ACCEPT
    Exact independently accepted dense-failure observability technical subject:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    R1: CLOSED
    Dense-failure observability IR-002 acceptance-record authority:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
      — AUTHORIZED
    Exact acceptance-record parent:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    Exact IR-002 acceptance-record tip:
      9f9734efb7a534f054415b32c73c039ae59369e3
    Human technical acceptance:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-001 — ACCEPTED
    Exact Human-accepted technical subject:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    HA-record authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-AUTH-001
      — AUTHORIZED
    Exact HA-record parent:
      9f9734efb7a534f054415b32c73c039ae59369e3
    Technical lineage (durable):
      91dba2e2885346ee595b920fd7dd02f671d2f7af
        — IR-004 ACCEPT (historical 16K-B subject)
      → f4707b828a85dcc538fc1510a52ed416d7a89935
        — post-qual chunk-ID remediation IR-001 ACCEPT
      → 349de6a55f0f362a42e646d946f0433cb33e6489
        — post-qual lexical zero-term remediation IR-001 ACCEPT
      → fbc8bb17a51f800aaa8bcc030c163427d8dc1821
        — lexical zero-term IR-001 acceptance-record tip
      → 6f61f18441c2348faa81a1852196b7d300a1c4da
        — dense-failure observability IR-001 REWORK REQUIRED (R1)
      → 40c6eb3824ac9f9c1cbc35c889e3e4110b229469
        — exact technical subject; IR-002 ACCEPT; HA-001 ACCEPTED; R1 CLOSED
      → 9f9734efb7a534f054415b32c73c039ae59369e3
        — IR-002 durable acceptance-record tip
      → 4f2c045717e2f8fe5b583173847a3bfa97046061
        — durable HA-record tip; HA-RECORD-IR-001 ACCEPT;
          not the technical HA subject
    HA-record IR:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-IR-001 — ACCEPT
    Exact accepted HA-record subject:
      4f2c045717e2f8fe5b583173847a3bfa97046061
    Fireground CUDA/cublasGemmEx runtime issue:
      OPEN / SEPARATE / NOT FIXED
    Branch: implementation/16k-b-ingestion-observability
  16K baseline evidence: FROZEN / INDEPENDENTLY ACCEPTED
    Campaign authority:
      S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001 — AUTHORIZED
    AUTH-open:
      S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-OPEN-001
    Exact AUTH-open execution pin:
      eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e
    Exact governance parent:
      4f2c045717e2f8fe5b583173847a3bfa97046061
    Technical subject under measurement:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    Freeze subject:
      S16-K-BASELINE-EVIDENCE-FREEZE-001
    Independent review:
      S16-K-BASELINE-EVIDENCE-FREEZE-IR-001 — REWORK REQUIRED (R1–R4)
    Exact IR-001 subject:
      0d169ae62d620709b220e8ebc97b2932d64a843b
    Rework authority:
      S16-K-BASELINE-EVIDENCE-FREEZE-REWORK-AUTH-001 — AUTHORIZED
    Exact rework parent:
      0d169ae62d620709b220e8ebc97b2932d64a843b
    Independent review:
      S16-K-BASELINE-EVIDENCE-FREEZE-IR-002 — ACCEPT
    Exact independently accepted freeze subject:
      3abc3a6c0ef31cc255ea6de8796203d26700ec23
    Human disposition:
      HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS
    Regression:
      workspace query/conversation HTTP 500
      after retrieval-model initialization
    Diagnostic authority:
      S16-K-POST-BASELINE-LIVE-QUERY-REGRESSION-DIAGNOSTIC-AUTH-001
      — AUTHORIZED
    Exact diagnostic parent:
      3abc3a6c0ef31cc255ea6de8796203d26700ec23
    Diagnostic branch: diagnostic/16k-live-query-regression
    Observability remediation authority:
      S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
      — AUTHORIZED
    Exact remediation parent:
      b65d1beda2ef8e19e59acebe498043b4188712c5
    Exact AUTH-open pin:
      0894a54bf5c8c8a06c0ec4821ebf3d804a92fc15
    Remediation branch: implementation/16k-query-failure-observability
    Remediation status: COMPLETE / READY FOR INDEPENDENT REVIEW
    Exact remediation review subject:
      9a8d30333bdc9fad800411b861bb05d2a038ea35
    Remediation scope:
      durable internal_failure + server traceback for grounded-query
      internal_error; public D08 / GET /v1/trace/{id} sanitized;
      no VRAM/device/CUDA behavioral fix
    Public projection:
      GET /v1/trace/{id} allowlist excludes internal_failure
    Device/VRAM/CUDA behavior: unchanged
    Manifest: docs/slice16k_baseline_evidence_campaign.md
    Freeze narrative: docs/slice16k_baseline_evidence.md
    Evidence: docs/evidence/16k_baseline/
    Accepted B0–B3 evidence: retained / not rewritten
    Fireground CUDA/cublasGemmEx:
      OPEN / SEPARATE / NOT FIXED
  16K-C: NOT AUTHORIZED
  16K-D: NOT AUTHORIZED
  16K-E → 16K-G: NOT AUTHORIZED
  Main promotion: NOT AUTHORIZED
16L: COMPLETE / ACCEPTED
  Authority: S16-L-EMBEDDING-AUTO-DEVICE-UX-AUTH-002
  Exact accepted subject: 88fadc7c3e8e70c4886cbff0c7863cccc63ef14a
  Embedding accelerator auto-selection + Compute settings
16M: COMPLETE / ACCEPTED
  Authority: S16-M-GOLD-POOL-AUX-INDEX-AUTH-001
  Exact accepted subject: dcf6bf02a77a4e68678d8887f836c471448422bc
16N: DESIGN FROZEN
  Authority: S16-N-GOLD-EXPERT-ENTRY-AUTH-001
  Q1–Q11 FROZEN
16N-A: COMPLETE / INDEPENDENTLY ACCEPTED
  Authority: S16-N-A-IMPLEMENTATION-AUTH-001
  Independent review: S16-N-A-IMPLEMENTATION-IR-002 — ACCEPT
  Exact accepted technical subject:
    36de7feaab33fddf77d4bdf5818f3cc60e8a1832
  Presentation Review bootstrap (non-mutating)
  Human QC presentation disposition:
    S16-N-A-QC-PRESENTATION-HA-001 — ACCEPTED
  QC ALLOW_PRODUCTION: ACCEPTED SUBJECT
    21dfb3e88920c40fe227d51efc8022995ef41c9e
  Human RF presentation disposition:
    S16-N-A-RF-PRESENTATION-HA-001 — ACCEPTED
  RF ALLOW_PRODUCTION: ACCEPTED SUBJECT
    Authority: S16-N-A-RF-ALLOW-PRODUCTION-AUTH-001
    Exact accepted subject:
      aac51029f279f07cafd1078160efbd592d5fc4be
  Evidence Sweep: NOT APPROVED
  Chunk Duel: NOT APPROVED
16N-B: COMPLETE / HUMAN ACCEPTED
  Authority: S16-N-B-IMPLEMENTATION-AUTH-001
  Frozen design: S16-N-GOLD-EXPERT-ENTRY-DESIGN-FREEZE-001
  Independent review: S16-N-B-IMPLEMENTATION-IR-003 — ACCEPT
  Human acceptance: S16-N-B-HA-001 — ACCEPTED
  Exact Human-accepted technical subject:
    ae137649565881ed295dc51dba422446fa81e682
  Prior reviewed lineage:
    IR-001: 1b993b5a111f18a0b8148e57e597b5332fe17179 — REWORK REQUIRED
    IR-002: 244e064356ad99ff65589acdecd60eb9cce60022 — REWORK REQUIRED
    IR-003: ae137649565881ed295dc51dba422446fa81e682 — ACCEPT
  IR-003 acceptance-record successor:
    c704ba4752225f8204195015fecc5e2ae4feea44
  16J: NOT AUTHORIZED FROM THIS DISPOSITION
  16K: NOT AUTHORIZED FROM THIS DISPOSITION
  Authoring-server failure UX defect: CLOSED
Authoring-server failure UX design: ACCEPTED
  Authority: S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-AUTH-001
  Design freeze: S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-FREEZE-001 — ACCEPTED / FROZEN
    (amended by R1–R4)
  Design doc: docs/slice16_closure_authoring_failure_ux_design.md
  Independent design review: S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-IR-003 — ACCEPT
  Exact accepted design subject:
    5922e0b9fa9f8986b23d801507b879a321124395
  Prior design review lineage:
    IR-001: ea95a2fe5261a42c8d841a4789f6aed1b9028cc7 — REWORK REQUIRED
    IR-002: 5faae42410ee38ef9e291a94f496a0a48da5739b — REWORK REQUIRED
    IR-003: 5922e0b9fa9f8986b23d801507b879a321124395 — ACCEPT
  Design rework R1–R4: ACCEPTED / FROZEN
  Q1–Q7 ACCEPTED / FROZEN (amended by R1–R4)
Authoring-server failure UX: COMPLETE / HUMAN ACCEPTED
  Authority: S16-CLOSURE-AUTHORING-FAILURE-UX-IMPLEMENTATION-AUTH-001 — AUTHORIZED
  Exact implementation base:
    5922e0b9fa9f8986b23d801507b879a321124395
  Branch: implementation/s16-closure-authoring-failure-ux
  Independent implementation review:
    S16-CLOSURE-AUTHORING-FAILURE-UX-IMPLEMENTATION-IR-001 — ACCEPT
  Human acceptance: S16-CLOSURE-AUTHORING-FAILURE-UX-HA-001 — ACCEPTED
  Exact Human-accepted technical subject:
    5cb63dad7344b9f6a3766ef83760801f375b5217
  IR acceptance-record tip:
    6591c07c5c61d4cf3eb41cd445f3bcc602fb78b2
  Pre-Human gate-footer successor:
    b7871738a5d986f24d9e9408ea0aa696f34f6e91
  Implementation-review handoff / docs tip:
    133f9c37cb82d8541e3347a0eec3d9c246f4ac0d
  Status: COMPLETE / HUMAN ACCEPTED
  Original misleading server-unreachable defect: CLOSED
  Repository lint baseline: STILL RED (pre-existing; not a candidate regression)
  Slice 16 final closeout: NOT AUTHORIZED FROM THIS DISPOSITION
Accepted-lineage documentation reconciliation: AUTHORIZED
  Authority: S16-ACCEPTED-LINEAGE-RECONCILIATION-AUTH-001 — AUTHORIZED
  Purpose: docs-only correction of RF accepted status and 16H
    BuildKit-secret CA wording before canonical promotion
  Exact base: 19694dac3cc9d405621f297bb1a237359a1c7327
  Does NOT claim: Slice 16 complete, 16J resumed, 16K/9G/17 authorized,
    or canonical main promotion complete
16J FINAL BRANDING: COMPLETE / HUMAN ACCEPTED / CANONICAL
  Design freeze: S16-J-REOPEN-BRANDING-UX-DESIGN-FREEZE-001 — ACCEPTED / FROZEN
  Implementation authority: S16-J-FINAL-BRANDING-IMPLEMENTATION-AUTH-001 — AUTHORIZED
  Acceptance-record authority:
    S16-J-FINAL-BRANDING-IR-002-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
  Design doc: docs/slice16j_final_branding.md
  Canonical technical base:
    09407ae0e5186b262a0b034e752672424e237fa2
  Branch: implementation/16j-final-branding
  Independent review:
    S16-J-FINAL-BRANDING-IMPLEMENTATION-IR-002 — ACCEPT
  Exact independently accepted technical subject:
    8208f86e3c4bb2508d35048ceb0ba9033f3de2ef
  Human acceptance: S16-J-FINAL-BRANDING-HA-001 — ACCEPTED
  Exact Human-accepted technical subject:
    8208f86e3c4bb2508d35048ceb0ba9033f3de2ef
  IR-002 acceptance-record tip:
    65aced367d92f3b411d476676f532c1727c78d70
  HA-001 acceptance-record tip:
    29d74c3a884d10f222eab07b92411e5a921bbba8
  F001: CLOSED
  MAIN PROMOTION COMPLETE
  Promotion authority:
    S16-J-FINAL-BRANDING-MAIN-PROMOTION-AUTH-001 — EXECUTED
  Promotion target / pre-reconciliation main:
    29d74c3a884d10f222eab07b92411e5a921bbba8
  Canonical main carries Human-accepted technical subject:
    8208f86e3c4bb2508d35048ceb0ba9033f3de2ef
  Product: Seneca — Grounded knowledge workspace
  Author: Carlos A. Schrupp
  Contact: carlos.schrupp@berkeley.edu
  Does NOT close Slice 16
Slice-16 closeout inventory: HUMAN ACCEPTED
  Authority: S16-CLOSEOUT-INVENTORY-AUTH-001 — AUTHORIZED
  HA acceptance-record authority:
    S16-CLOSEOUT-INVENTORY-HA-001-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
  Exact inventory base: 168af70b54fba39f0efba69100d57b41a574667f
  Artifact: docs/slice16_closeout_inventory.md
  Historical IR-002 ACCEPT (exact subject d284776…): remains valid provenance
  IR-002 acceptance-record authority:
    S16-CLOSEOUT-INVENTORY-IR-002-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
  IR-002 acceptance-record tip (provenance): 5df7af2…
  I-32 amendment + IR-003 F003 wording correction: historical
  Independent review: S16-CLOSEOUT-INVENTORY-IR-004 — ACCEPT
  Human acceptance: S16-CLOSEOUT-INVENTORY-HA-001 — ACCEPTED
  Exact Human-accepted inventory subject:
    e24c11df70a59c41c494f302a19ae211bf787bf9
  Human acceptance of d284776…: NOT GRANTED — superseded as Human
    acceptance target by e24c11d…
  Historical inventory verdict (at inventory HA):
    CLOSEOUT BLOCKED — REQUIRED RESIDUALS REMAIN
  Live technical residual verdict: CLEAR
  Authoritative residual set (closed):
    I-26, I-27, I-28, I-30, I-31, I-32
    HUMAN ACCEPTED / CLOSED
  Reconciliation authority:
    S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-AUTH-001 — AUTHORIZED
  Exact reconciliation base: 73b7fc99d7dc24930962f40a584ed957de4e716a
  Reconciliation IR-001: REWORK REQUIRED (F001)
  Reconciliation IR-002: ACCEPT
  IR-002 acceptance-record authority:
    S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
    — AUTHORIZED
  IR-002 acceptance-record tip:
    e7305f06df22da4898e2246c40bf256c9535ccad
  Exact Human-accepted reconciliation subject:
    fc36aa8013a90b6355e85d97a00dc145b5802cd5
  Human acceptance:
    S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-HA-001 — ACCEPTED
  HA acceptance-record authority:
    S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-HA-001-ACCEPTANCE-RECORD-AUTH-001
    — AUTHORIZED
  HA acceptance-record tip:
    3b36630952f34a147c3c8e82fdec7c0649620c0b
  Reconciliation status: COMPLETE / HUMAN ACCEPTED
  Final Slice-16 closeout authority:
    S16-FINAL-CLOSEOUT-AUTH-001 — AUTHORIZED
  Exact final-closeout base:
    3b36630952f34a147c3c8e82fdec7c0649620c0b
  Exact Human-accepted final-closeout subject:
    c4ba1e7956a6812279fdf45f28c24738856dec44
  Independent review: S16-FINAL-CLOSEOUT-IR-001 — ACCEPT
  Human acceptance: S16-FINAL-CLOSEOUT-HA-001 — ACCEPTED
  HA acceptance-record authority:
    S16-FINAL-CLOSEOUT-HA-001-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
  Final Slice-16 closeout: HUMAN ACCEPTED / CANONICAL
  Technical residual verdict: CLEAR
  Repairs I-26…I-32: HUMAN ACCEPTED / CLOSED
  HA acceptance-record tip:
    feab2b2778aeec2f73b8a6f64f8d82e7921ae2a6
  Canonical main promotion: COMPLETE / EXECUTED
  Main-promotion authority:
    S16-FINAL-CLOSEOUT-MAIN-PROMOTION-AUTH-001 — EXECUTED
  Post-promotion record authority:
    S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-AUTH-001 — AUTHORIZED
  Exact Human-accepted post-promotion record subject:
    76caab2a68ef42c0c2b216b7e3b3e989ab4d56b3
  Post-promotion record IR-001: ACCEPT
  Post-promotion record HA-001: ACCEPTED
  Post-promotion record HA acceptance-record authority:
    S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-HA-001-ACCEPTANCE-RECORD-AUTH-001
    — AUTHORIZED
  Post-promotion record status: COMPLETE / HUMAN ACCEPTED / CANONICAL
  HA acceptance-record tip lineage:
    e21b3e6013c743d7d09f13836704dd88969d4d4a
  Current canonical origin/main:
    e21b3e6013c743d7d09f13836704dd88969d4d4a
  Second main promotion (HA acceptance-record tip): COMPLETE / EXECUTED
  Second-promotion authority:
    S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-HA-MAIN-PROMOTION-AUTH-001
    — EXECUTED
  Second-promotion record authority:
    S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-HA-MAIN-PROMOTION-RECORD-AUTH-001
    — AUTHORIZED
  Second promotion operation: PURE FAST-FORWARD
  Pre-second-promotion canonical main:
    feab2b2778aeec2f73b8a6f64f8d82e7921ae2a6
  Promoted canonical main (second FF):
    e21b3e6013c743d7d09f13836704dd88969d4d4a
  Target vs canonical main after second promotion: 0 / 0
  Historical pre-second-promotion live claim (at tip e21b3e6… as authored):
    This HA acceptance-record successor: NOT YET PROMOTED TO MAIN
    (provenance only)
  Promotion operation: PURE FAST-FORWARD
  Pre-promotion canonical main:
    168af70b54fba39f0efba69100d57b41a574667f
  Promoted canonical main:
    feab2b2778aeec2f73b8a6f64f8d82e7921ae2a6
  Target vs canonical main after promotion: 0 / 0
  Historical pre-promotion live claim (at HA tip feab2b2…):
    Canonical main promotion: NOT AUTHORIZED / NOT YET EXECUTED
    (provenance only)
  Scope: docs/governance only; no product code; no 16K/9G/17/18
9G: DEFERRED / NOT AUTHORIZED
16K: DESIGN ACCEPTED / FROZEN
  Design-open: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001 — AUTHORIZED
  Rework: S16-K-BETA-INGESTION-READINESS-DESIGN-REWORK-AUTH-001 — AUTHORIZED
    (addresses DESIGN-OPEN-IR-001 R1–R5)
  Human acceptance: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-001 — ACCEPTED
  HA record: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-AUTH-001 — AUTHORIZED
  HA-record IR: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-IR-001 — ACCEPT
  Exact Human-accepted design subject:
    0839b565cd60958141366048520236a71bf16fd0
  Design: docs/slice16k_beta_ingestion_readiness_design.md
  Detached managed-ingest lifetime ≠ HTTP request deadline; transport safety
    ≠ searchable workload
  Frozen order: 16K-A → 16K-B → baseline evidence → 16K-C → 16K-D
    → 16K-E → 16K-F → 16K-G
  16K-A: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
    Implementation authority:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-AUTH-001 — AUTHORIZED
    Independent review:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-IR-002 — ACCEPT
    Human acceptance:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-HA-001 — ACCEPTED
    HA record:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-AUTH-001 — AUTHORIZED
    Exact Human-accepted technical subject:
      1370b99327124045ad96005e829095683842c06f
    Branch: implementation/16k-a-managed-ingestion-correctness
    HA-record IR:
      S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-IR-001 — ACCEPT
  16K-B: COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED /
    HA RECORD INDEPENDENTLY ACCEPTED
    Implementation authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-AUTH-001 — AUTHORIZED
    Exact implementation base:
      39e5e09363193b2315ada9e56cb3e1c14ba9377d
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-001 — REWORK REQUIRED (R1–R4)
    Rework authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-001 — AUTHORIZED
    Exact rework base:
      85f01f40080fe485b6ddb7700855aa34280c9c75
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-002 — REWORK REQUIRED (R3 / R4a / R4b)
    Rework authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-002 — AUTHORIZED
    Exact rework-002 base / parent:
      533a07c3d1313d08eae5647e4c266d4fa3a439c5
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-003 — REWORK REQUIRED (R3 orphan ownership)
    Rework authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-003 — AUTHORIZED
    Exact rework-003 base / parent:
      2c0e7bf21c8c427ee99b1b9518342a8080596463
    Independent review:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004 — ACCEPT
    IR-004 acceptance-record authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
    Exact independently accepted technical subject (IR-004 historical):
      91dba2e2885346ee595b920fd7dd02f671d2f7af
    Post-qualification remediation authority:
      S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-AUTH-001 — AUTHORIZED
    Exact post-qual remediation parent:
      037a39531abfd5f5335151a946dbede776c5f492
    Post-qualification chunk-ID collision IR:
      S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-IR-001 — ACCEPT
    Exact chunk-ID collision remediation subject:
      f4707b828a85dcc538fc1510a52ed416d7a89935
    Post-qualification lexical zero-term eligibility remediation authority:
      S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-AUTH-001
      — AUTHORIZED
    Exact lexical zero-term remediation parent:
      f4707b828a85dcc538fc1510a52ed416d7a89935
    Post-qualification lexical zero-term eligibility IR:
      S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001 — ACCEPT
    Exact independently accepted lexical zero-term remediation subject:
      349de6a55f0f362a42e646d946f0433cb33e6489
    Lexical zero-term IR-001 acceptance-record authority:
      S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001-ACCEPTANCE-RECORD-AUTH-001
      — AUTHORIZED
    Exact acceptance-record parent:
      349de6a55f0f362a42e646d946f0433cb33e6489
    Exact lexical zero-term IR-001 acceptance-record tip:
      fbc8bb17a51f800aaa8bcc030c163427d8dc1821
    Post-qualification dense-failure observability remediation authority:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
      — AUTHORIZED
    Exact dense-failure observability remediation parent:
      fbc8bb17a51f800aaa8bcc030c163427d8dc1821
    Post-qualification dense-failure observability IR:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-001
      — REWORK REQUIRED (R1)
    Exact dense-failure observability IR-001 subject:
      6f61f18441c2348faa81a1852196b7d300a1c4da
    Dense-failure observability rework authority:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001
      — AUTHORIZED
    Exact dense-failure observability rework parent:
      6f61f18441c2348faa81a1852196b7d300a1c4da
    Dense-failure observability rework IR:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002
      — ACCEPT
    Exact independently accepted dense-failure observability technical subject:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    R1: CLOSED
    Dense-failure observability IR-002 acceptance-record authority:
      S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
      — AUTHORIZED
    Exact acceptance-record parent:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    Exact IR-002 acceptance-record tip:
      9f9734efb7a534f054415b32c73c039ae59369e3
    Human technical acceptance:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-001 — ACCEPTED
    Exact Human-accepted technical subject:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    HA-record authority:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-AUTH-001
      — AUTHORIZED
    Exact HA-record parent:
      9f9734efb7a534f054415b32c73c039ae59369e3
    Technical lineage (durable):
      91dba2e2885346ee595b920fd7dd02f671d2f7af
        — IR-004 ACCEPT (historical 16K-B subject)
      → f4707b828a85dcc538fc1510a52ed416d7a89935
        — post-qual chunk-ID remediation IR-001 ACCEPT
      → 349de6a55f0f362a42e646d946f0433cb33e6489
        — post-qual lexical zero-term remediation IR-001 ACCEPT
      → fbc8bb17a51f800aaa8bcc030c163427d8dc1821
        — lexical zero-term IR-001 acceptance-record tip
      → 6f61f18441c2348faa81a1852196b7d300a1c4da
        — dense-failure observability IR-001 REWORK REQUIRED (R1)
      → 40c6eb3824ac9f9c1cbc35c889e3e4110b229469
        — exact technical subject; IR-002 ACCEPT; HA-001 ACCEPTED; R1 CLOSED
      → 9f9734efb7a534f054415b32c73c039ae59369e3
        — IR-002 durable acceptance-record tip
      → 4f2c045717e2f8fe5b583173847a3bfa97046061
        — durable HA-record tip; HA-RECORD-IR-001 ACCEPT;
          not the technical HA subject
    HA-record IR:
      S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-IR-001 — ACCEPT
    Exact accepted HA-record subject:
      4f2c045717e2f8fe5b583173847a3bfa97046061
    Fireground CUDA/cublasGemmEx runtime issue:
      OPEN / SEPARATE / NOT FIXED
    Branch: implementation/16k-b-ingestion-observability
  16K baseline evidence: FROZEN / INDEPENDENTLY ACCEPTED
    Campaign authority:
      S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001 — AUTHORIZED
    AUTH-open:
      S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-OPEN-001
    Exact AUTH-open execution pin:
      eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e
    Exact governance parent:
      4f2c045717e2f8fe5b583173847a3bfa97046061
    Technical subject under measurement:
      40c6eb3824ac9f9c1cbc35c889e3e4110b229469
    Freeze subject:
      S16-K-BASELINE-EVIDENCE-FREEZE-001
    Independent review:
      S16-K-BASELINE-EVIDENCE-FREEZE-IR-001 — REWORK REQUIRED (R1–R4)
    Exact IR-001 subject:
      0d169ae62d620709b220e8ebc97b2932d64a843b
    Rework authority:
      S16-K-BASELINE-EVIDENCE-FREEZE-REWORK-AUTH-001 — AUTHORIZED
    Exact rework parent:
      0d169ae62d620709b220e8ebc97b2932d64a843b
    Independent review:
      S16-K-BASELINE-EVIDENCE-FREEZE-IR-002 — ACCEPT
    Exact independently accepted freeze subject:
      3abc3a6c0ef31cc255ea6de8796203d26700ec23
    Human disposition:
      HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS
    Regression:
      workspace query/conversation HTTP 500
      after retrieval-model initialization
    Diagnostic authority:
      S16-K-POST-BASELINE-LIVE-QUERY-REGRESSION-DIAGNOSTIC-AUTH-001
      — AUTHORIZED
    Exact diagnostic parent:
      3abc3a6c0ef31cc255ea6de8796203d26700ec23
    Diagnostic branch: diagnostic/16k-live-query-regression
    Observability remediation authority:
      S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
      — AUTHORIZED
    Exact remediation parent:
      b65d1beda2ef8e19e59acebe498043b4188712c5
    Exact AUTH-open pin:
      0894a54bf5c8c8a06c0ec4821ebf3d804a92fc15
    Remediation branch: implementation/16k-query-failure-observability
    Remediation status: COMPLETE / READY FOR INDEPENDENT REVIEW
    Exact remediation review subject:
      9a8d30333bdc9fad800411b861bb05d2a038ea35
    Remediation scope:
      durable internal_failure + server traceback for grounded-query
      internal_error; public D08 / GET /v1/trace/{id} sanitized;
      no VRAM/device/CUDA behavioral fix
    Public projection:
      GET /v1/trace/{id} allowlist excludes internal_failure
    Device/VRAM/CUDA behavior: unchanged
    Manifest: docs/slice16k_baseline_evidence_campaign.md
    Freeze narrative: docs/slice16k_baseline_evidence.md
    Evidence: docs/evidence/16k_baseline/
    Accepted B0–B3 evidence: retained / not rewritten
    Fireground CUDA/cublasGemmEx:
      OPEN / SEPARATE / NOT FIXED
  16K-C: NOT AUTHORIZED
  16K-D: NOT AUTHORIZED
  16K-E → 16K-G: NOT AUTHORIZED
  Main promotion: NOT AUTHORIZED
  Does NOT reopen Slice 16 closeout
  Does NOT authorize main promotion
SLICE 16: COMPLETE / HUMAN ACCEPTED / CANONICAL
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
BASELINE: 1610f9282d1edbd4dfc8ae76d7644a1b9ea4e75e
```

This plan decomposes Slice 16 into sequential phase gates. Plan acceptance does
**NOT** authorize execution. Coding still requires explicit per-phase
implementation authorization. 16A, 16B, and 16C have been separately authorized,
implemented, reviewed, and **ACCEPTED**. Later phases remain gated.

Locked design authority: [`docs/slice16_design_authority.md`](slice16_design_authority.md)
(S16-D01 … S16-D35) at AUTHORITY SHA
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`.

Amendment A1 (**ACCEPTED / LOCKED** supplemental design authority):
[`docs/slice16_amendment_a1_seneca_product_ux.md`](slice16_amendment_a1_seneca_product_ux.md)
at `5060e2aeb4825f265072a1f870c3c963eace3b30`.

Amendment A2 (**ACCEPTED / LOCKED / SEALED** at
`dce3456e519cb6c96570e20f5af800d00cafb5a7`; governance closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`):
[`docs/slice16_amendment_a2_conversational_grounding.md`](slice16_amendment_a2_conversational_grounding.md).
A2 authoritatively supersedes only its enumerated clauses and revises the Ask
path into **16D-B1 (observed) / 16D-B2 / 16D-B3** then **16D-C**. A2 acceptance
did **not** by itself authorize B2/B3/C. B1 foundation upload remediation is
**ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`); that acceptance does **not**
grant product acceptance to the legacy B1 Ask/Evidence UX. **16D-B2** is
**COMPLETE / ACCEPTED / SEALED** at
`baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`. **16D-B3** is **COMPLETE / ACCEPTED / SEALED** at
`9c178ffb033cde41849379fc914f321697ff8691` (A3 **ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`; see
[`docs/slice16d_b3_conversational_workspace.md`](slice16d_b3_conversational_workspace.md)).
**16D-C** is **COMPLETE / ACCEPTED / SEALED** (see
[`docs/slice16d_c_training_mode.md`](slice16d_c_training_mode.md)).

16A evidence: [`docs/slice16a_workspace_foundation.md`](slice16a_workspace_foundation.md)

16B evidence: [`docs/slice16b_workspace_lifecycle_api.md`](slice16b_workspace_lifecycle_api.md)

16C evidence: [`docs/slice16c_react_shell_source_ui.md`](slice16c_react_shell_source_ui.md)

16D-A evidence: [`docs/slice16d_a_seneca_product_foundation_query_scope.md`](slice16d_a_seneca_product_foundation_query_scope.md)

16D-B1 foundation remediation evidence:
[`docs/slice16d_b1_upload_foundation_remediation.md`](slice16d_b1_upload_foundation_remediation.md)

16D-B2 evidence:
[`docs/slice16d_b2_grounded_answer_v2.md`](slice16d_b2_grounded_answer_v2.md)

```text
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

---

## Phase order

Use sequential phase gates unless explicitly redesigned:

```text
16A [ACCEPTED]
 ↓
16B [ACCEPTED]
 ↓
16C [ACCEPTED / SEALED]
 ↓
16D-A [COMPLETE / ACCEPTED / SEALED]
 ↓
16D-B1 [OBSERVED CANDIDATE / PRODUCT ACCEPTANCE WITHHELD]
 ↓
B1 foundation remediation [ACCEPTED / SEALED @ c68cc3f8… / closeout b5fa1e85…]
 ↓
16D-B2 [COMPLETE / ACCEPTED / SEALED @ baa16eba…]   ← Grounded Answer V2
 ↓
16D-B3 [COMPLETE / ACCEPTED / SEALED @ 9c178ffb… / A3 da1082d9…]
        ← Conversational workspace
 ↓
16D-C [COMPLETE / ACCEPTED / SEALED]
 ↓
16E [COMPLETE / ACCEPTED / SEALED]
 ↓
16F [COMPLETE / ACCEPTED / SEALED]
 ↓
16G-D0 [ACCEPTED / FROZEN]
 ↓
16G-I1…I5 / GAP-16G-01 [ACCEPTED]
 ↓
GAP-16G-02 [CLOSEOUT ACCEPTED @ HA-001 / IR-002; subject e5d116b8…;
            main promotion COMPLETE at f7fb999…]
 ↓
16G-I6 [COMPLETE / ACCEPTED @ cc7ff520eb146fa555f2b48e1f7dcc89a7952729]
 ↓
16H [COMPLETE / ACCEPTED @ 01a4a984… / 16H-HA-001]
```

```text
AMENDMENT A1: ACCEPTED / LOCKED
5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
dce3456e519cb6c96570e20f5af800d00cafb5a7
docs/slice16_amendment_a2_conversational_grounding.md
A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
```

Under accepted A2, Ask/Evidence decomposes into **B1 / B2 / B3** (see A2-D24).
**16D-A** is **COMPLETE / ACCEPTED / SEALED**. Observed B1 candidate
`6b652400…` remains **PRODUCT ACCEPTANCE WITHHELD / NOT SEALED**. B1
foundation upload remediation is **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`). **16D-B2** is
**COMPLETE / ACCEPTED / SEALED** at
`baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`. **16D-B3** is **COMPLETE / ACCEPTED / SEALED** at
`9c178ffb033cde41849379fc914f321697ff8691` (A3 **ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`; see
[`docs/slice16d_b3_conversational_workspace.md`](slice16d_b3_conversational_workspace.md)).
**16D-C** is **COMPLETE / ACCEPTED / SEALED**.

Do not close Slice 16 automatically after 16H. Independent review and explicit
human acceptance of the implemented slice remain required. **16A**, **16B**,
**16C**, **16D-A**, and **16D-B2** are **COMPLETE / ACCEPTED**; legacy B1
product UX acceptance remains **WITHHELD**; B1 foundation remediation is
**ACCEPTED / SEALED**; **16D-B3** is **COMPLETE / ACCEPTED / SEALED**; **16D-C** and
Amendment **A4** are **COMPLETE / ACCEPTED / SEALED** at
`0381e0461f68c5fc09e7be2c7699d434e8b8a9cb`; **16E** is **COMPLETE /
ACCEPTED / SEALED** (Engineering `3e1ce4c94fc511abb4e1d94bd194736d5497e64f`;
Workspace source-loading remediation `9dd2b008ebf9feee279dc6d0e58fafb006288ee5`);
**16F** is **COMPLETE / ACCEPTED / SEALED** at
`f25f8358aead7fcfe161fff388012cec23b5a573` (closeout
[`docs/slice16f_closeout.md`](slice16f_closeout.md)). **16G-D0** is **ACCEPTED / FROZEN**
([`docs/slice16g_gold_lab_games_pedagogy_design.md`](slice16g_gold_lab_games_pedagogy_design.md)).
**16G-I1…I5** and **GAP-16G-01** are **ACCEPTED**. **GAP-16G-02** is **CLOSEOUT ACCEPTED** (`HA-001`; IR-002 **ACCEPT**;
exact subject `e5d116b8a2990f3b0ac7f3fe1cbf052b4f6ac087`; main promotion
**COMPLETE** at `f7fb999…`) (closeout
[`docs/gap16g_02_gold_baseline_bootstrap_closeout.md`](gap16g_02_gold_baseline_bootstrap_closeout.md)).
**16G-I6** is **COMPLETE / ACCEPTED** (IR-002 **ACCEPT**; exact candidate
`cc7ff520eb146fa555f2b48e1f7dcc89a7952729`). **16G** is **IMPLEMENTATION
COMPLETE / ACCEPTED**. **16H** is **COMPLETE / ACCEPTED** (16H-IR-003
**ACCEPT**; 16H-HA-001 **ACCEPTED**; exact subject
`01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10`). **9G** remains
**DEFERRED / NOT AUTHORIZED**. Slice 16 overall is **COMPLETE /
HUMAN ACCEPTED / CANONICAL** (`S16-FINAL-CLOSEOUT-IR-001` — ACCEPT;
`S16-FINAL-CLOSEOUT-HA-001` — ACCEPTED; exact subject `c4ba1e7…`;
technical residual verdict **CLEAR**; canonical main promotion
**COMPLETE / EXECUTED** at `feab2b2…`).

---

## 16A — Workspace contracts & persistence foundation

```text
STATUS: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
Evidence: docs/slice16a_workspace_foundation.md
```

### Scope

- workspace/source identities;
- metadata/revisions (presentation metadata vs scientific publication);
- empty-workspace / depublication state contract (S16-D07 / S16-D13);
- raw-source vault;
- operation/idempotency records;
- tombstone models;
- application use-case boundaries;
- error taxonomy extensions (including empty/not-ready query);
- **NO UI**.

### Must not

- mutate scientific pipeline semantics;
- bypass `offline_rag.app`;
- auto-publish unfinished candidates;
- fabricate empty scientific snapshots;
- treat display-only metadata edits as snapshot-creating mutations.

### Depends on

- accepted Slice 15 product/API surface;
- locked Slice 16 design authority
  (`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`).

### Acceptance focus

- durable workspace/source/revision models;
- empty workspace validity (`current_snapshot_id = null`, `sources = []`);
- depublication / retirement storage semantics preserving historical artifacts
  while clearing active current publication;
- distinct workspace revision advancement for display-only metadata vs
  content/membership publication;
- vault privacy under `/data`;
- idempotency/revision record shapes without HTTP yet;
- scoring contract/version identifier may be deferred until 16F unless naturally
  part of shared contract scaffolding.

---

## 16B — Workspace/source lifecycle API

```text
STATUS: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
AUTHORIZED BASELINE: 155983fec59a3ae6434286276bd34dcfdaaf8968
ACCEPTED 16A SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16C: COMPLETE / ACCEPTED @ 936e41446eb1e3697f6b7d245659831f19cf0613
16D+: NOT AUTHORIZED
Evidence: docs/slice16b_workspace_lifecycle_api.md
```

### Inherited contracts from accepted 16A

These are inherited implementation contracts (not new design scope). Accepted 16B
MUST:

- use `WorkspaceMutationLease` → `CorpusMutationLease` lock order (never
  reverse);
- integrate outstanding EMPTY-journal recovery into startup/readiness before
  workspace mutation/query surfaces become ready;
- never call retirement/restore publication helpers without holding the corpus
  mutation lease;
- compose `ManagedOperationStore` with already-held workspace leases where
  orchestration requires one atomic mutation section.

### Scope

- workspace CRUD;
- source CRUD;
- source replace;
- full-snapshot projection for non-empty membership mutations;
- final-source removal EMPTY / depublication transition (S16-D13);
- display-only metadata PATCH without snapshot rebuild (S16-D11);
- idempotency;
- ETag/revision concurrency;
- managed mutation operations;
- operation status;
- workspace query adapter (fail closed when EMPTY);
- source content delivery.

### Critical acceptance

1. Normal add / remove / replace (non-empty result) publishes a new immutable
   snapshot (S16-D11).
2. `manual_b_v05` with `OLD_MARKER` → replace `manual_b_v06` with `NEW_MARKER`
   → current N+1 retrieval/context/citations/answer contain no `OLD_MARKER`
   (S16-D12).
3. Final-source removal: one-source workspace → remove final source → workspace
   EMPTY (`sources = []`, `current_snapshot_id = null`) → old source not
   queryable through current workspace/product path; no empty Slice-15 ingest;
   crash leaves either prior one-source+publication or committed EMPTY with no
   active publication (S16-D13).
4. Display-only rename: workspace revision advances; `snapshot_id` remains
   unchanged (S16-D11).
5. Byte-identical replacement creates a new source version iff the operation is
   accepted as a new version; `document_id` changes iff content identity
   changes; idempotent retry does not create another source version (S16-D09).
6. Crash/interruption of unfinished candidate never becomes current (S16-D15).
7. Stale `If-Match` / conflicting idempotency keys fail closed (S16-D14).

### Must not

- build a second RAG pipeline;
- introduce `/eval/*`;
- auto-resume scientific ingest after crash;
- fabricate empty scientific snapshots;
- rebuild corpus on display-only metadata edits.

---

## 16C — React shell, design system & source-management UI

```text
STATUS: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
AUTHORIZED BASELINE: a0a8a3f9a38807f40676a9a249cd7c7b186c09cb
ACCEPTED 16B SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16D+: NOT AUTHORIZED
Evidence: docs/slice16c_react_shell_source_ui.md
```

### Scope

- React/TS/Vite shell;
- same-origin production static delivery;
- routing;
- TanStack Query;
- design tokens (S16-D06);
- responsive nav;
- Overview;
- workspace library;
- source management;
- operation progress UX;
- offline-bundled assets;
- WCAG foundations.

### Must not

- fake data in production surfaces;
- runtime CDN dependency under strict offline;
- Redux by default;
- scientific controls in source UI.

---

## 16D-A — Seneca Product Foundation & Query-Scope Substrate

```text
STATUS: COMPLETE / ACCEPTED
IMPLEMENTATION: 4f8962f2893ab433e6ea269ad54e46f67771ca70
AMENDMENT A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
AUTHORIZED BASELINE: 185d3e3d2bd472ffaddf72cfddc49c7e38a3a146
EVIDENCE: docs/slice16d_a_seneca_product_foundation_query_scope.md
```

Authoritative under accepted Amendment A1. **16D-A** is **COMPLETE / ACCEPTED**
at `4f8962f2893ab433e6ea269ad54e46f67771ca70`. **16D-B / 16D-C** remain
**NOT AUTHORIZED / NOT STARTED**.

### Accepted scope

- Seneca brand application; provisional stoa favicon/logo; canonical title;
- compact source rail; source `⋮` CRUD; de-emphasized metadata management;
- compact operation completion UX; capacity presentation;
- explicit internal YAML capacity defaults; read-only capabilities endpoint;
- Settings cog/page; generation runtime configuration API/persistence;
- product-managed local/LAN approval (not Internet under strict-offline);
- operator/environment locks that cannot be bypassed from the UI;
- endpoint/model probe against prospective policy (no activate/persist on probe);
- ACTIVE vs PENDING configuration; restart-required semantics;
- source-scoped query DTO; server-side source→document binding;
- dense + lexical pre-ranking scope enforcement; scoped-query provenance.

### Must not

- implement full Ask/Evidence UX merely because the query substrate exists;
- weaken generation allow-list security or approve public Internet endpoints
  under strict-offline merely because Settings accepted typed input;
- bypass operator/environment locks with product-managed approvals;
- activate or persist generator configuration from Test Connection alone;
- report PENDING generator settings via capabilities as if ACTIVE;
- hot-swap live generation clients without restart-required semantics;
- treat source checkboxes as workspace membership mutations.

---

## 16D-B — Ask & Evidence Workspace (decomposed under accepted A2)

```text
AMENDMENT A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED @ dce3456e519cb6c96570e20f5af800d00cafb5a7
A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
PREREQUISITE 16D-A: COMPLETE / ACCEPTED / SEALED @ 4f8962f2893ab433e6ea269ad54e46f67771ca70
LAST SEALED IMPLEMENTATION BASELINE:
  a952a75bc07191b213a5113eee53cb967fef8326
```

Historical A1 text treated 16D-B as a single Ask/Evidence gate (single-turn Ask,
citation chips, session-local history). Accepted A2 authoritatively replaces
that with B1/B2/B3 below. Do **not** implement B2/B3/C without separate
authorization.

### 16D-B1 — Ask/Evidence Engineering Foundation

```text
STATUS: OBSERVED IMPLEMENTATION CANDIDATE
PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
OBSERVED SHA: 6b6524001f063a628505f572e7ca13d954a38260
HISTORICAL DISPOSITION: useful engineering substrate;
  legacy product UX acceptance withheld
EVIDENCE (historical): docs/slice16d_b_ask_evidence_workspace.md
```

Useful substrate preserved (not release-accepted Ask UX):

- source selection;
- scoped query;
- exact-version evidence;
- Current / Historical semantics;
- PDF / text evidence preview;
- session presentation primitives.

Known A2 product findings remain assigned downstream (not fixed by upload
remediation):

- F7 desktop shell too narrow → B3
- F8 dynamic content spill/containment → B3
- F9 composer lifecycle → B3
- F10 single-turn interaction too primitive → B3

### 16D-B1 FOUNDATION REMEDIATION

```text
STATUS: ACCEPTED / SEALED
ACCEPTED IMPLEMENTATION:
  c68cc3f8f16a2588ba093886f3e48e1c7037f83f
VERIFIED CLOSEOUT:
  b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
INDEPENDENT CLOSEOUT REVIEW: PASSED
IMPLEMENTATION BASELINE:
  6b6524001f063a628505f572e7ca13d954a38260
EVIDENCE: docs/slice16d_b1_upload_foundation_remediation.md
FINDINGS CLOSED: B1-U1 / B1-U2 / B1-U3 / B1-U4 / B1-R1
```

Accepted upload-foundation scope only (does **not** grant legacy B1 product
UX acceptance):

- browser multi-file source-upload reliability;
- pre-202 AbortController / cancellation;
- honest transport-error classification;
- transport-ambiguity-safe idempotent retry;
- R1 canceled-upload fresh-intent duplicate hazard fix.

### 16D-B2 — Grounded Answer V2 & Claim Citations

```text
STATUS: COMPLETE / ACCEPTED / SEALED
ACCEPTED IMPLEMENTATION: baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
REWORK 1: COMPLETE
EVIDENCE: docs/slice16d_b2_grounded_answer_v2.md
```

Delivered (A2-D12–D18 / B2 portion of A2-D24): response-local E1/E2 handles;
Grounded Answer V2 blocks; excerpts; claim citation cards; structured
abstention. **No** conversational orchestration in B2.

### 16D-B3 — Conversational Workspace

```text
STATUS: COMPLETE / ACCEPTED / SEALED

ACCEPTED IMPLEMENTATION:
9c178ffb033cde41849379fc914f321697ff8691

INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
REWORK 1: COMPLETE
REWORK 2: COMPLETE
REWORK 3: COMPLETE
REWORK 3A: COMPLETE

AUTHORIZED BASELINE:
28aad06f89e6d00a0b81b51f9c2de38fed06cb22

REWORK 3 BASELINE:
528e7dbb10fdde24ea1ea7db71a4e35c2a9222e1

AMENDMENT A3:
ACCEPTED / LOCKED / SEALED
MATERIALIZATION: da1082d95630c12eaf0ce1a3b8d005aaa60d2f73

EVIDENCE:
docs/slice16d_b3_conversational_workspace.md

16D-C:
NOT AUTHORIZED / NOT STARTED
```

**Accepted / sealed scope:** B3 on
`implementation/16d-b3-conversational-workspace` at `9c178ffb033cde41849379fc914f321697ff8691` provides
conversation/turn orchestration; bounded contextual resolver; fresh retrieval
through the shared scientific core; New conversation / composer lifecycle;
per-turn provenance; Current/Historical behavior; Grounded Answer V2 claim
citations; full-viewport desktop workspace under Amendment A3; independently
collapsible desktop Sources/Evidence rails; hard overflow containment; and
responsive narrow drawers. Owns F7/F8/F9/F10 where applicable.

**Historical prerequisites (already satisfied — not active gates):** B3
activation required verified B2 closeout and branching from the authorized B2
closeout / B3 baseline. Those prerequisites were met; B3 is no longer “not yet
started” or awaiting B2 activation.

### Must not (all B* gates)

- factual conversational memory / prior answers as evidence;
- second RAG pipeline;
- fabricate PDF text highlights without reliable mapping;
- treat B1 foundation remediation acceptance as legacy Ask UX acceptance;
- treat B3 acceptance as automatic C acceptance
  (**16D-C** is now separately **COMPLETE / ACCEPTED / SEALED**; later gates remain unauthorized).

---

## 16D-C — Training Mode

```text
STATUS: COMPLETE / ACCEPTED / SEALED
ACCEPTED IMPLEMENTATION: 0381e0461f68c5fc09e7be2c7699d434e8b8a9cb
INDEPENDENT REVIEW: PASSED
HUMAN ACCEPTANCE: ACCEPTED
EVIDENCE: docs/slice16d_c_training_mode.md
CLOSEOUT: docs/slice16d_c_a4_closeout.md
AMENDMENT A4: ACCEPTED / LOCKED / SEALED
AMENDMENT A1: ACCEPTED / LOCKED @ 5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED @ dce3456e519cb6c96570e20f5af800d00cafb5a7
AUTHORIZED BASELINE: 396aa329e6c0413eb69aacd39067a70d9b478b72
BRANCH: implementation/16d-c-training-mode
```

### Accepted implementation scope

- **required** instructor-oriented Training Mode (S16-D19 — not optional);
- saved prompts seed / start conversation turns (A2-D25);
- hide/reveal answer / citations / evidence on grounded assistant turns;
- larger presentation-friendly typography;
- optional fullscreen/presentation layout;
- frontend-only pedagogical layer over accepted B3 conversation path.

### Must not

- LMS / accounts / grading;
- treat Training Mode as deferred/optional Slice-16 scope;
- second RAG path / training-specific scientific pipeline.

---

## Historical note — former monolithic 16D gate

Prior plan text treated Ask, Evidence, and Training Mode as a single **16D**
gate. Accepted Amendment A1 subdivided that gate into **16D-A / 16D-B / 16D-C**
for implementation governance. Phase execution remains separately gated.

---

## 16E — Engineering Evidence

### Scope

- deterministic accepted-evidence exporter;
- static UI evidence manifest;
- Evaluation page;
- pipeline comparisons from accepted artifacts;
- performance evidence;
- safety/robustness evidence;
- Architecture page;
- provenance drill-down.

### Must not

- `/eval/*` runtime API;
- scientific controls / run-benchmark buttons;
- numeric zero for missing telemetry;
- claim publication-grade results beyond existing artifact governance.

---

## 16F — Gold Lab data plane

```text
STATUS: COMPLETE / ACCEPTED / SEALED
FINAL TIP: f25f8358aead7fcfe161fff388012cec23b5a573
INDEPENDENT IMPLEMENTATION REVIEW: ACCEPT
HUMAN TECHNICAL ACCEPTANCE: ACCEPTED
INDEPENDENT CLOSEOUT REVIEW: ACCEPT
HUMAN CLOSURE ACCEPTANCE: ACCEPTED
CLOSURE-READY TIP REVIEWED: f273d2d570a052672e46ece7f6200508c4015b36
CLOSEOUT: docs/slice16f_closeout.md
```

### Scope

- Gold projects/campaigns;
- append-only judgment ledger;
- atomic resumable tasks;
- projection into existing Silver/HumanReview;
- benchmark vs improvement project type;
- selection policy provenance;
- snapshot/chunk-set binding;
- corrections/supersession;
- canonical export/registration;
- Gold Contribution score as effective-state projection with scoring
  contract/version identifier (S16-D34) — not raw append-event count.

### Must preserve

- existing `GoldDataset` v1;
- Silver→Gold boundary;
- human-finalized absolute relevance as canonical;
- exact `snapshot_id` / `chunk_set_id` binding;
- append-only ledger as audit source while score uses effective unique
  completed contributions.

### Must not

- auto-promote model labels to gold;
- migrate historical gold by filename/fuzzy text;
- automatically change retrieval defaults from new gold;
- inflate contribution score from idempotent retries or superseding
  corrections.

---

## 16G — Gold Lab games & pedagogical training compiler

```text
STATUS: 16G-D0 ACCEPTED / FROZEN; I1–I5 / GAP-16G-01 ACCEPTED;
        GAP-16G-02 CLOSEOUT ACCEPTED (HA-001 / IR-002; subject e5d116b8…);
        MAIN PROMOTION COMPLETE at f7fb999…;
        I6 COMPLETE / ACCEPTED; 16G IMPLEMENTATION COMPLETE / ACCEPTED
DESIGN TIP: 8af2dbab72d1a79f53b0f3958e7c7142b4273693
DESIGN BLOB: edc2be739621dbedfc44ed77861119a35f8f6d18
FROZEN DESIGN: docs/slice16g_gold_lab_games_pedagogy_design.md
GAP-16G-01: ACCEPTED
GAP-16G-02:
  CLOSEOUT ACCEPTED
  IR-002 ACCEPT / HA-001 ACCEPTED
  HUMAN-ACCEPTED SUBJECT: e5d116b8a2990f3b0ac7f3fe1cbf052b4f6ac087
  ACCEPTED IMPLEMENTATION: 120c03cd79f3af142144a6b73e05bcb43fdacb76
  ACCEPTED DESIGN: 4b872cc0e9caf3323196cc2c3afe4772e249f191
  CLOSEOUT: docs/gap16g_02_gold_baseline_bootstrap_closeout.md
  MAIN PROMOTION: COMPLETE
  PROMOTED MAIN: f7fb999758ce6219be27d27a3f1c0a16ece97506
16G-I6: COMPLETE / ACCEPTED
  Independent review: 16G-I6-IR-002 — ACCEPT
  Human technical acceptance: ACCEPTED
  Exact accepted candidate: cc7ff520eb146fa555f2b48e1f7dcc89a7952729
16G: IMPLEMENTATION COMPLETE / ACCEPTED
16H: COMPLETE / ACCEPTED
  Independent review: 16H-IR-003 — ACCEPT
  Human acceptance: 16H-HA-001 — ACCEPTED
  Exact Human-accepted subject: 01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10
SLICE 16: COMPLETE / HUMAN ACCEPTED / CANONICAL
Authority: 16G-D0-AUTH-001 / Human acceptance ACCEPTED
```

### Scope

- Rapid Fire;
- Evidence Sweep;
- Question Check;
- Chunk Duel;
- calibration mode;
- `presentation_id` tracking;
- workload chooser;
- Gold contribution dashboard;
- source-grounded pedagogy;
- gold-derived evidence drills;
- scenario/debrief presentation.

### Must

- keep Chunk Duel auxiliary (not silent absolute gold);
- keep learner actions from creating gold;
- calibrate presentation variants before production-quality gold use.

### Must not

- happy/sad emotional relevance faces;
- leaderboards / speed rewards / model-agreement rewards;
- decorative cognitive-load fire imagery.

---

## 16H — Integration / accessibility / portfolio acceptance

### Scope

- cross-surface integration;
- responsive acceptance;
- WCAG 2.2 AA audit;
- keyboard-only flows;
- source supersession integration;
- operation recovery UX;
- strict-offline/static-asset checks;
- container/static delivery verification;
- portfolio evidence consistency;
- no fake data;
- final Slice-16 integration harness;
- **empirical source/corpus capacity validation** on a declared local reference
  machine (Amendment A1 candidate; e.g. 32 / 64 / 128 sources and increasing
  active-source byte totals). Defaults must not be raised by intuition alone.

### Must not

- self-accept Slice 16;
- authorize Slice 17 / Slice 18 / M7 closeout;
- claim globally green unrelated suites;
- promise NotebookLM-equivalent cloud capacity.

### Exit condition

Evidence candidate + independent review + explicit human acceptance only.

---

## Explicit non-scope (entire Slice 16 plan)

- authentication / multi-tenant product;
- LMS / certification;
- factual conversational memory / prior assistant answers as evidence
  (accepted A2 narrower rule; **not** a blanket ban on linguistic multi-turn
  grounding — prior-turn linguistic context through the bounded A2 resolver
  is in scope and was accepted via A2/B3; scientific answering continues to
  rely on fresh retrieval through the canonical grounded-query path);
- permanent secure purge/GC;
- distributed queues / multi-worker redesign;
- issue #1 image-size optimization;
- Slice 17 / Slice 18 / Milestone 7 closeout.

### Registered product-flow gap — GAP-16G-02

**Status:** **CLOSEOUT ACCEPTED / PROMOTED TO MAIN** (`HA-001`; IR-002 **ACCEPT**; subject `e5d116b8…`; main promotion **COMPLETE** at `f7fb999…`)

Seneca now includes the accepted baseline-bootstrap product path that creates
the pristine GoldAuthoringRun baseline Gold Lab campaign creation requires.
Accepted implementation: `120c03cd79f3af142144a6b73e05bcb43fdacb76`.
Closeout candidate:
[`docs/gap16g_02_gold_baseline_bootstrap_closeout.md`](gap16g_02_gold_baseline_bootstrap_closeout.md).

Product path (accepted):

```text
workspace publication
→ 9B propose
→ 9C pool
→ optional 9D advisory prelabel
→ pristine-baseline validation
→ Gold Lab
```

Detail: [`docs/slice16g_gap_registry_addendum.md`](slice16g_gap_registry_addendum.md).

This closeout projection does **not** amend frozen 16G-D0, does **not** reopen
Slice **9G** (**DEFERRED / NOT AUTHORIZED**), and does **not** place
`NEXT-MILESTONE-CANDIDATE-01` (answer-level user feedback) into 16G
implementation scope.

---

## Authorization note

```text
IMPLEMENTATION PLAN: ACCEPTED
DESIGN AUTHORITY: ACCEPTED / LOCKED
AUTHORITY SHA: e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
16A: COMPLETE / ACCEPTED
ACCEPTED SHA: e73959be508541a1c50d4919606aaf3157a5fa8a
16B: COMPLETE / ACCEPTED
ACCEPTED SHA: eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
16C: COMPLETE / ACCEPTED
ACCEPTED SHA: 936e41446eb1e3697f6b7d245659831f19cf0613
AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30
AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7
  A2 CLOSEOUT: f0bdf78d0ae6a79737055d324b22fc35e1e501f5
16D-A: COMPLETE / ACCEPTED / SEALED
IMPLEMENTATION: 4f8962f2893ab433e6ea269ad54e46f67771ca70
OBSERVED 16D-B1 CANDIDATE:
  6b6524001f063a628505f572e7ca13d954a38260
  PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
16D-B1 FOUNDATION REMEDIATION:
  ACCEPTED / SEALED
  ACCEPTED IMPLEMENTATION: c68cc3f8f16a2588ba093886f3e48e1c7037f83f
  VERIFIED CLOSEOUT: b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
  INDEPENDENT CLOSEOUT REVIEW: PASSED
16D-B2: COMPLETE / ACCEPTED / SEALED
  ACCEPTED IMPLEMENTATION: baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
  INDEPENDENT REVIEW: PASSED
  HUMAN ACCEPTANCE: ACCEPTED
  REWORK 1: COMPLETE
16D-B3: COMPLETE / ACCEPTED / SEALED
        ACCEPTED IMPLEMENTATION: 9c178ffb033cde41849379fc914f321697ff8691
        INDEPENDENT REVIEW: PASSED
        HUMAN ACCEPTANCE: ACCEPTED
        REWORK 1: COMPLETE
        REWORK 2: COMPLETE
        REWORK 3: COMPLETE
        REWORK 3A: COMPLETE
        AUTHORIZED BASELINE: 28aad06f89e6d00a0b81b51f9c2de38fed06cb22
        A3: ACCEPTED / LOCKED / SEALED
        A3 MATERIALIZATION: da1082d95630c12eaf0ce1a3b8d005aaa60d2f73
        EVIDENCE: docs/slice16d_b3_conversational_workspace.md
        A3 DOC: docs/slice16_amendment_a3_full_viewport_workspace.md
16D-C: COMPLETE / ACCEPTED / SEALED
AMENDMENT A4: ACCEPTED / LOCKED / SEALED
16E: COMPLETE / ACCEPTED / SEALED
  ACCEPTED ENGINEERING IMPLEMENTATION: 3e1ce4c94fc511abb4e1d94bd194736d5497e64f
  WORKSPACE SOURCE-LOADING REMEDIATION: 9dd2b008ebf9feee279dc6d0e58fafb006288ee5
  REMEDIATION EVIDENCE TIP: 9cd5528ab6c6e22d2dca55aca221b65eac50269e
  EVIDENCE: docs/slice16e_engineering_evidence.md
  REMEDIATION: docs/workspace_source_loading_remediation.md
  CLOSEOUT: docs/slice16e_closeout.md
16F: COMPLETE / ACCEPTED / SEALED
  FINAL TIP: f25f8358aead7fcfe161fff388012cec23b5a573
  CLOSEOUT: docs/slice16f_closeout.md
16G-D0: ACCEPTED / FROZEN
  DESIGN TIP: 8af2dbab72d1a79f53b0f3958e7c7142b4273693
  DESIGN BLOB: edc2be739621dbedfc44ed77861119a35f8f6d18
  FROZEN DESIGN: docs/slice16g_gold_lab_games_pedagogy_design.md
16G-I1…I5: ACCEPTED
GAP-16G-01: ACCEPTED
GAP-16G-02:
  CLOSEOUT ACCEPTED
  IR-002 ACCEPT / HA-001 ACCEPTED
  HUMAN-ACCEPTED SUBJECT: e5d116b8a2990f3b0ac7f3fe1cbf052b4f6ac087
  ACCEPTED IMPLEMENTATION: 120c03cd79f3af142144a6b73e05bcb43fdacb76
  ACCEPTED DESIGN: 4b872cc0e9caf3323196cc2c3afe4772e249f191
  CLOSEOUT: docs/gap16g_02_gold_baseline_bootstrap_closeout.md
  MAIN PROMOTION: COMPLETE
  PROMOTED MAIN: f7fb999758ce6219be27d27a3f1c0a16ece97506
16G-I6: COMPLETE / ACCEPTED
  Independent review: 16G-I6-IR-002 — ACCEPT
  Human technical acceptance: ACCEPTED
  Exact accepted candidate: cc7ff520eb146fa555f2b48e1f7dcc89a7952729
16G: IMPLEMENTATION COMPLETE / ACCEPTED
16H: COMPLETE / ACCEPTED
  Independent review: 16H-IR-003 — ACCEPT
  Human acceptance: 16H-HA-001 — ACCEPTED
  Exact Human-accepted subject: 01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10
SLICE 16: COMPLETE / HUMAN ACCEPTED / CANONICAL
SLICE 17: NOT AUTHORIZED
SLICE 18: NOT AUTHORIZED
9G: DEFERRED / NOT AUTHORIZED
M7 CLOSEOUT: NOT AUTHORIZED
```

Plan acceptance alone did **not** authorize execution. 16A, 16B, 16C,
16D-A, and 16D-B2 were separately authorized and are now **COMPLETE /
ACCEPTED**. Amendment A1 is **ACCEPTED / LOCKED** at
`5060e2aeb4825f265072a1f870c3c963eace3b30`. Amendment A2 is **ACCEPTED /
LOCKED / SEALED** at `dce3456e519cb6c96570e20f5af800d00cafb5a7` (closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`). **16D-A** is **COMPLETE /
ACCEPTED / SEALED** at `4f8962f2893ab433e6ea269ad54e46f67771ca70`. Observed
16D-B1 candidate `6b652400…` remains **PRODUCT ACCEPTANCE WITHHELD**. B1
foundation remediation is **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`). **16D-B2** is **COMPLETE /
ACCEPTED / SEALED** at `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`.
**16D-B3** is **COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691` (A3
**ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`). **16D-C** and
Amendment **A4** are **COMPLETE / ACCEPTED / SEALED** at
`0381e0461f68c5fc09e7be2c7699d434e8b8a9cb`. **16E** is **COMPLETE /
ACCEPTED / SEALED** (Engineering `3e1ce4c94fc511abb4e1d94bd194736d5497e64f`;
Workspace source-loading remediation `9dd2b008ebf9feee279dc6d0e58fafb006288ee5`;
evidence tip `9cd5528ab6c6e22d2dca55aca221b65eac50269e`). **16F** is
**COMPLETE / ACCEPTED / SEALED** at
`f25f8358aead7fcfe161fff388012cec23b5a573` (closeout
`docs/slice16f_closeout.md`). **16G-D0** is **ACCEPTED / FROZEN**
(`docs/slice16g_gold_lab_games_pedagogy_design.md` at tip
`8af2dbab72d1a79f53b0f3958e7c7142b4273693`). **16G-I1…I5** and **GAP-16G-01**
are **ACCEPTED**. **GAP-16G-02** is **CLOSEOUT ACCEPTED** (`HA-001`; IR-002 **ACCEPT**;
subject `e5d116b8…`; main promotion **COMPLETE** at `f7fb999…`)
([`docs/gap16g_02_gold_baseline_bootstrap_closeout.md`](gap16g_02_gold_baseline_bootstrap_closeout.md);
[`docs/slice16g_gap_registry_addendum.md`](slice16g_gap_registry_addendum.md)).
**16G-I6** is **COMPLETE / ACCEPTED** (IR-002 **ACCEPT**; exact candidate
`cc7ff520eb146fa555f2b48e1f7dcc89a7952729`). **16G** is **IMPLEMENTATION
COMPLETE / ACCEPTED**. **16H** is **COMPLETE / ACCEPTED** (16H-IR-003
**ACCEPT**; 16H-HA-001 **ACCEPTED**; exact subject
`01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10`). **9G** remains
**DEFERRED / NOT AUTHORIZED**. Slice 16 overall is **COMPLETE /
HUMAN ACCEPTED / CANONICAL** (`S16-FINAL-CLOSEOUT-IR-001` — ACCEPT;
`S16-FINAL-CLOSEOUT-HA-001` — ACCEPTED; exact subject `c4ba1e7…`;
technical residual verdict **CLEAR**; canonical main promotion
**COMPLETE / EXECUTED** at `feab2b2…`).
