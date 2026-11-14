# Slice 18 — Portfolio Release Program

This document is the canonical planning definition for the remaining Slice 18
work. Registration here is not implementation or execution authority. Each
slice remains subject to its own authorization and review.

## Current state

- **18A — Engineering Evidence Reconciliation:** COMPLETE / HUMAN ACCEPTED /
  PROMOTED.
- **18B Revision 2 — Workstation Distribution:** COMPLETE / HUMAN ACCEPTED /
  PROMOTED.
- **18C — Universal Workstation Distribution & Release Optimization:**
  AUTHORIZED / IMPLEMENTATION AND QUALIFICATION COMPLETE / INDEPENDENT REVIEW
  PENDING at `9e2cf563737cf4c9a927753c7768f5e4897b1a7f`.
- **18D — Product Metrics Audit and Explainability:** PLANNED / NOT AUTHORIZED.
- **18E — Canonical Documentation and Portfolio Narrative:** PLANNED /
  NOT AUTHORIZED.
- **18F — Public Release and Demo Assembly:** PLANNED / NOT AUTHORIZED.
- **Milestone 7 closeout:** NOT AUTHORIZED.

Slice 18B's deferred real-host checks remain:

- `SYSTEMD_USER_RUNTIME = DEFERRED_REAL_HOST_VALIDATION`
- `WSL_DISTRO_LIFECYCLE = DEFERRED_REAL_HOST_VALIDATION`

They are not implementation gates for Slices 18C–18F unless later evidence or
authority explicitly makes them so.

## 18C — Universal Workstation Distribution & Release Optimization

### Objective

Provide one clear, user-consumable workstation distribution that installs a
lean CPU baseline and can optionally enable CUDA with explicit user approval.
Also publish immutable CPU and CUDA container variants. GitHub Releases is the
intended first public distribution channel for workstation artifacts.

The intended public workstation artifact is one universal package:

```text
seneca-workstation-<version>-linux-x86_64-<sha>.tar.gz
```

CPU and CUDA are not separate Seneca products. The workstation package is one
application distribution; CUDA is an optional runtime/dependency extension.
Containers remain immutable dependency-specific artifacts.

### Universal workstation lifecycle

The baseline install must be fully functional on CPU, contain no unnecessary
CUDA/NVIDIA dependency payload, preserve the qualified CPU/ONNX path, and allow
later explicit CUDA enablement when compatible hardware is available.

Use the existing Seneca hardware/runtime probe and compute resolver. The
installer/upgrader must not implement a second hardware-selection system.
`embedding.device = auto | cpu | cuda` remains authoritative:

```text
AUTO + usable CUDA
  → cuda_fp16_v1
  → torch_st_v1
  → PyTorch / SentenceTransformers
  → CUDA FP16

AUTO + CUDA unavailable
  → cpu_onnx_fp32_v1
  → onnx_fp32_v1
  → ONNX Runtime
  → CPUExecutionProvider
```

Explicit CPU/CUDA selection and existing fail-closed unsupported combinations
remain unchanged.

When a compatible NVIDIA GPU is detected, the workstation may offer CUDA
enablement. Activation requires explicit user consent, transactional
preparation of a CUDA-capable environment (including provisioning `torch_st_v1`
if required), validation before activation, and restart/activation through
the existing versioned release/environment model. A failed CUDA enablement
must leave the working CPU installation usable. Do not download CUDA
dependencies merely because a GPU is present. The CUDA extension is optional
and must not be downloaded by CPU-only users.

Future controls may be CLI or UI operations conceptually like
`seneca enable-cuda` and `seneca disable-cuda`; this planning amendment does
not lock their exact interface.

### Immutable container variants

Containers remain dependency-specific and immutable:

```text
seneca:<version>-cpu
seneca:<version>-cuda
```

The CPU container is the default/general-purpose artifact for CPU-only
deployments, CI/reproducible CPU execution, ordinary cloud CPU deployments,
and Google Cloud portfolio/demo deployment when no GPU is provisioned. It
must not contain unnecessary CUDA/NVIDIA runtime dependency weight.

The CUDA container is for intentional deployment on compatible NVIDIA hosts.
Both images contain the same Seneca application semantics and existing
compute resolver; only dependency/runtime payload differs.

### Qualification boundary

18C packages the already-qualified dual-backend architecture; it does not
redesign or requalify `cpu_onnx_fp32_v1`, `cuda_fp16_v1`, AUTO selection
semantics, CPU/CUDA scientific validity, embedding algorithms, reranking,
retrieval, Gold truth, generation behavior, or UI product semantics. A
demonstrated packaging blocker may be corrected within 18C, but it does not
reopen those contracts by itself.

### User-facing requirements

- CPU guidance states that a compatible NVIDIA GPU is not required.
- CUDA guidance states supported NVIDIA/CUDA prerequisites and fails clearly
  when they are unavailable or incompatible.
- Users should not need to understand dependency extras or internal runtime
  package names to install or enable the supported profile.

### Distribution-size objective

- CPU-only workstation users download only the CPU baseline.
- Workstation CUDA dependencies are downloaded only after explicit enablement.
- CPU cloud/container deployments do not carry CUDA dependency weight.
- NVIDIA container deployments use the CUDA image.
- Seneca application behavior is not forked.

Do not define arbitrary size thresholds in this plan. Authorized 18C work
measures actual artifact/image sizes and dependency composition.

### Distribution principles

End users should not need to clone the Git repository, build the React
frontend, understand internal dependency profiles, or install application
source manually.

Do not bundle NVIDIA drivers, system CUDA drivers/toolkits unless separately
justified, Ollama, generator model weights, retrieval model weights, or private
data. Preserve strict-offline runtime after provisioning, the local Ollama
boundary, `/data` and `/models` separation, versioned application releases,
package integrity/provenance, and AUTO compute selection.

Package-manager distribution, MSI/MSIX, apt repositories, auto-update, macOS,
ARM, and native-Windows installers are outside 18C unless separately
authorized.

## 18D — Product Metrics Audit and Explainability

### Objective

Audit every user-visible metric, score, status, percentage, count, timing,
resource value, and derived indicator in Seneca. A portfolio application must
not display a metric that cannot be precisely explained and defended.

For every metric, establish:

- name;
- source;
- formula or derivation;
- unit;
- eligible population;
- aggregation semantics;
- missing/unavailable behavior;
- range, where applicable;
- interpretation and what it does **not** imply;
- provenance;
- tests; and
- UI wording.

No metric may remain merely decorative or ambiguous. If a metric is incorrect,
stale, ambiguously named, derived from the wrong population, presented with
misleading precision, impossible to reproduce, or unsupported by available
evidence, correct it or remove it.

Audit all user-visible categories, including retrieval, evaluation, Gold/Gold
Lab, game/contribution scores, workspace/source counts, progress/state,
ingestion statistics, benchmark/performance, latency, resource/compute
information, model/backend identity, CPU/CUDA state, and derived product
scores or percentages.

Keep scientific metrics distinct from operational/product metrics. Performance
measurements retain the accepted descriptive/no-SLO interpretation unless a
separate authority establishes an SLO.

For every displayed number, a reviewer should be able to ask, “Where did this
value come from, what exactly does it mean, and how do you know it is correct?”
Seneca's implementation and documentation should provide a precise answer.

## 18E — Canonical Documentation and Portfolio Narrative

### Objective

Make public repository documentation pristine, internally consistent,
technically accurate, and understandable to a competent external reviewer
without project history. 18E follows 18D so final documentation uses audited
metric definitions rather than unstable semantics.

Canonical documentation should clearly answer:

- What is Seneca, and what problem does it solve?
- What runs locally, and what can use external inference?
- What does strict-offline mean, and what data leaves the machine under each
  supported profile?
- What are `/data` and `/models`, and which models are used?
- How do ingestion, dense retrieval, BM25, RRF, reranking, and context assembly
  work?
- How are answers grounded, and how are citations constructed and validated?
- What are Gold and Gold Lab, and what are the production-approved games for?
- What does every displayed metric mean?
- How do CPU and CUDA execution differ? Why does CPU embedding use ONNX? What
  does AUTO compute selection do?
- What is Ollama's role?
- How do Docker and workstation installations differ, and how are models
  provisioned?
- What benchmark evidence exists, which claims are descriptive rather than
  prescriptive, and what limitations remain?
- What functionality is deferred, and how does a user install, run, and
  troubleshoot Seneca?

Public documentation must not require knowledge of historical slice
discussions. Preserve historical evidence where needed, mark it
historical/superseded, and remove stale instructions from public-facing
navigation. Create or reconcile a canonical metric glossary from the accepted
18D audit. Do not introduce unsupported performance, quality, security, or
privacy claims.

## 18F — Public Release and Demo Assembly

### Objective

Assemble the accepted product, distribution artifacts, evidence, and
documentation into the public portfolio release.

Candidate deliverables include:

- GitHub Release;
- universal CPU-first workstation archive and checksum;
- immutable CPU and CUDA container artifacts;
- release notes;
- Docker and workstation instructions;
- demo/sample-corpus instructions and reproducible demo workflow;
- architecture diagram and metrics glossary;
- benchmark methodology/results and known limitations;
- screenshots and optional short demo video/GIF;
- optional hosted portfolio instance using the accepted REL-03 inference seam;
- final public-claims/evidence matrix.

Hosting is optional unless separately selected as a release requirement.

### Fresh-reviewer walkthrough

Perform a fresh-reviewer walkthrough using only public artifacts and public
documentation. It must not require tribal knowledge, unpublished commands,
prior ChatGPT conversations, private corpora, private model files, or hidden
environment assumptions. Any necessary undocumented knowledge is a release
defect.

Audit the final release for credentials, private paths, private corpora,
private prompts/content, model binaries not intended for redistribution, stale
claims, broken links, and obsolete setup instructions.

## Cross-slice principles

1. **No unexplained metric.** No metric ships publicly unless its semantics and
   provenance are precise.
2. **No undocumented runtime distinction.** CPU, CUDA, Docker, workstation,
   local inference, and external-inference profiles must be distinguishable
   and explainable.
3. **No unsupported public claim.** Every public quality, performance,
   privacy, security, or architecture claim maps to accepted evidence or is
   explicitly labeled as design/limitation rather than observed fact.
4. **No unnecessary product redesign.** Slices 18C–18F are release/product
   work. Do not reopen retrieval algorithms, Gold truth, reranker science,
   generation semantics, recovery, LangGraph, NeMo, `base.yaml` scientific
   promotion, publication-grade 9G, BETA-CONV-02, or other settled behavior
   unless an observed release blocker independently justifies it.
5. **Separate correctness from presentation.** Metric correctness precedes
   final metric documentation. Runtime/package correctness precedes release
   presentation. Public documentation describes accepted behavior rather than
   driving undocumented implementation changes.

## Remaining sequence

```text
18A Engineering Evidence Reconciliation
    COMPLETE / ACCEPTED / PROMOTED
        ↓
18B Workstation Distribution Revision 2
    COMPLETE / ACCEPTED / PROMOTED
        ↓
18C Universal Workstation Distribution & Release Optimization
    CPU-first universal workstation + optional CUDA extension
    immutable CPU/CUDA containers
        ↓
18D Product Metrics Audit and Explainability
    every user-visible metric correct and defensible
        ↓
18E Canonical Documentation and Portfolio Narrative
    coherent, external-facing documentation
        ↓
18F Public Release and Demo Assembly
    release / demo / final evidence-backed claims
        ↓
Milestone 7 closeout (NOT AUTHORIZED)
        ↓
End-to-end beta QA
        ↓
Release-blocking defects only
        ↓
Human beta acceptance
        ↓
RELEASE
```

Slice 18C implementation and available local qualification are **COMPLETE /
READY FOR INDEPENDENT REVIEW** under `S18C-UNIVERSAL-DISTRIBUTION-IMPL-001`.
The current implementation candidate is
`9e2cf563737cf4c9a927753c7768f5e4897b1a7f`; the workstation doctor corrective
was installed and tested through the exact packaged wrapper without repeating
CPU/CUDA qualification because it changes only diagnostic working-directory
handling.
This does not authorize promotion, registry publication, GitHub Release
publication, cloud deployment, or work on Slices 18D–18F. Slices 18D–18F and
Milestone 7 closeout remain
**PLANNED / NOT AUTHORIZED**.
