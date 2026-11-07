# Historical Challenge Coverage Map — Candidate

**Status:** Codex-prepared traceability proposal; independent completeness
review pending. This table does not claim that a reviewer confirmed every
BETA-CONV-01 IR-001 through IR-004 finding is represented.

| Stable case ID | Failure/edge family | Regression contract to verify |
| --- | --- | --- |
| `historical-summary-phrase` | Full conversation summary | Whole-history summary is routed to the supported transformation or safe clarification contract; no unsupported retrieval claim. |
| `historical-apostrophe-fence` | Malformed delimiter | Malformed quoted/fenced target is rejected safely without executing the wrong target. |
| `historical-quoted-format` | Named prior target and quoted format | Exact prior assistant target and supported bullet option are preserved. |
| `historical-100-bullets` | Unsupported option | Out-of-range formatting request is rejected/clarified; no clamped or invented option. |
| `historical-grammar-correction` | Grammar edit mistaken for source update | Editing intent is not reclassified as factual correction; unsupported ambiguity clarifies. |
| `historical-prior-topic` | Named prior target with topic words | Topic nouns inside the explicit prior-turn target do not force retrieval. |
| `historical-linked-using` | Linked source precedence (`using`) | External source link forces grounded routing ahead of prior-turn transformation. |
| `historical-linked-from` | Linked source precedence (`from`) | External source link forces grounded routing ahead of prior-turn transformation. |
| `historical-linked-based-on` | Linked source precedence (`based on`) | External source link forces grounded routing ahead of prior-turn transformation. |
| `historical-unknown-source` | Unknown source must clarify | Unresolved source reference does not silently broaden scope or execute retrieval. |
| `historical-injected-prior` | Prior turn is untrusted data | Injection in prior assistant text is treated as data, never as instruction or evidence. |
| `historical-multiple-targets` | Ambiguous multiple targets | Multiple candidate target spans do not cause arbitrary target execution. |
| `historical-source-transform-mix` | Mixed grounded and transformation obligations | Source verification takes precedence; no citation-free answer can satisfy a factual obligation. |

The roster has 13 unique stable IDs and one case for each named family except
the linked-source family, which has three paraphrase forms. Independent review
must map each accepted IR finding to one or more rows, identify any uncovered
finding, and verify the request/label semantics. The private held-out split is
not used for this review and has not been scored.
