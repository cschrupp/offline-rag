# Historical Challenge Coverage Map — Candidate

**Status:** Codex-prepared traceability proposal; independent completeness
review pending. This table does not claim that a reviewer confirmed every
BETA-CONV-01 IR-001 through IR-004 finding is represented.

| Stable case ID | Failure/edge family | Required historical outcome | Existing deterministic regression |
| --- | --- | --- | --- |
| `historical-summary-phrase` | Full conversation summary | `unsupported_operation` with `conversation_summary_unavailable`; no retrieval or transformation | `test_whole_conversation_summary_uses_unsupported_operation_contract` |
| `historical-apostrophe-fence` | Malformed delimiter | Safe rejection or exact recovered target; never execute a wrong span | `test_apostrophes_and_malformed_delimiters_do_not_hide_targets` |
| `historical-quoted-format` | Named prior target and quoted format | Exact prior assistant target and supported bullet option | `test_named_prior_target_takes_precedence_over_quoted_format_phrase` |
| `historical-100-bullets` | Unsupported option | Clarify; never clamp or invent an option | `test_unsupported_options_are_not_silently_dropped` |
| `historical-grammar-correction` | Grammar edit mistaken for source update | Safe clarification; no factual source-update route | `test_grammar_correction_is_not_classified_as_factual_source_update` |
| `historical-prior-topic` | Named prior target with topic words | Transform exact prior target; topic words do not force retrieval | `test_named_prior_turn_transform_wins_over_topic_source_words` |
| `historical-linked-using` | Linked source precedence (`using`) | Grounded route precedes prior-turn transformation | `test_source_oriented_request_stays_on_grounded_pipeline` |
| `historical-linked-from` | Linked source precedence (`from`) | Grounded route precedes prior-turn transformation | `test_source_oriented_request_stays_on_grounded_pipeline` |
| `historical-linked-based-on` | Linked source precedence (`based on`) | Grounded route precedes prior-turn transformation | `test_source_oriented_request_stays_on_grounded_pipeline` |
| `historical-unknown-source` | Unknown source must clarify | No silent scope broadening or retrieval | `test_planner_mode_http_rejects_unselected_source_reference_without_retrieval` |
| `historical-injected-prior` | Prior turn is untrusted data | Treat injected text as data, not instruction or evidence | `test_fabricated_assistant_instruction_stays_in_data_delimiters`; `test_prior_assistant_claims_not_evidence` |
| `historical-multiple-targets` | Ambiguous multiple targets | Clarify; do not select a target arbitrarily | `test_multiple_delimited_targets_clarify_instead_of_guessing` |
| `historical-source-transform-mix` | Mixed grounded and transformation obligations | Grounded verification takes precedence; citation-free transform cannot satisfy it | `test_source_oriented_request_stays_on_grounded_pipeline` |

The IR-004 linked-source examples and linked-source-inside-supplied-target
distinction are covered by the corresponding parameterized source-routing and
supplied-Markdown-text regressions. The whole-history summary rubric now follows
the accepted unsupported-operation contract and has a deterministic
orchestration regression.

The roster has 13 unique stable IDs and one case for each named family except
the linked-source family, which has three paraphrase forms. This is a
Codex-prepared traceability candidate, not an independent completeness
attestation. The reviewer must compare each finding in BETA-CONV-01 IR-001
through IR-004 against these rows and their referenced regressions, identify
any uncovered finding, and verify request/label semantics. The private
held-out split is not used for this review and has not been scored.
