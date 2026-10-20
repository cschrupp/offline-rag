# 16K-D D1 — Scientific interpretation (analysis-only rework)

**Analysis rework authority:** `S16-K-D-D1-SCIENTIFIC-ANALYSIS-PUBLICATION-REWORK-AUTH-001`  
**Sealed execution subject:** `177620a3440c310759775dbf303420b80df7a05c`  
**Sealed evidence tip (cells):** `4326586fe0ce3b7ca4c40ded743272d72ba53036`  
**Machine-readable analysis:** `d1_analysis.json` (`d1-frozen-analysis-v2`)

No new scientific encodes. Derived only from sealed A1 / A2 / B evidence.

## Execution validity

D1-A1, D1-A2, and D1-B are independently accepted as scientifically valid cells
(IR-001). This document repairs analysis publication only.

## What the sealed evidence supports

1. **Full-run latency structure is reproducible**  
   A1↔A2 batch-rank Spearman ≈ 0.90; both also correlate with D0 clean ranks.

2. **Intrinsic batch-content / simple shape is materially disfavored**  
   Targeted D1-B replay of historically fast/slow identities collapses the gap
   (~5.2–5.6 s means; 1↔14 ratio ≈ 0.96; 17↔13 ≈ 1.01). A1 shape correlations
   remain moderate-to-weak (max seq ≈ 0.46; tokens ≈ 0.30; padded ≈ 0.36;
   padding fraction ≈ 0).

3. **Host-only delay is materially disfavored**  
   Wall↔CUDA-device Pearson ≈ 1.0 in A1 and A2; residuals are hundreds of ms
   while stalls last tens of seconds. The explosion is represented in device
   elapsed time.

4. **Simple allocator / clock / thermal explanations are not established**  
   Reserved/peak allocator correlations are weak (~0.22–0.23). SM clock ~0.27;
   power ≈ uncorrelated. Software power-cap is Active on many both fast and
   slow batches; no thermal-throttle Active signals in A1/A2. Temperature
   associations are confounded with run progression.

5. **Leading unresolved class**  
   State/history-dependent GPU/model execution (same content slow in fresh
   full-index traversal, ~5 s in controlled one-model replay).

## D2 eligibility

**D2 comparisons are scientifically eligible**, provided later authorities use
controlled repeated-run design and control process/run history rather than
interpreting a single lucky run.

## Limits

No causal claim from correlation alone. D1 walls are attribution-only (not
§9.4 gates). D1 does not change production policy.
