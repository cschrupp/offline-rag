# Slice 17 IR-002 — Clean-checkout pre-correction skip inventory

**Commit tested:** `cf31ac0e2999aed5b0a3da59af3b3f0e890d593a`
**Required-lane result:** 142 passed, 67 skipped, 1 warning.
**Environment:** clean tracked clone; ignored local model/tokenizer artifacts absent; REL-03 variables unset; proxy egress pointed at closed loopback.
**Common skip reason:** `tiktoken artifacts not provisioned` from each suite's shared settings helper. None of these tests exercises tokenizer provisioning or tokenizer identity.

The exact command was the required backend CI pytest list with `-vv -rs`.
Each selected skipped node ID is listed below. The 67 are accidental required-lane skips, not intentional exclusions.

## `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py` — 14 skipped

- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_managed_ingest_ignores_request_deadline_sync_ingest_does_not` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_managed_and_sync_share_ingest_capacity_and_drain` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_client_disconnect_never_cancels_managed_ingest` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_sync_ingest_still_observes_configured_deadline` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_dense_batch_checkpoint_observes_shutdown` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_publication_critical_section_ignores_shutdown_for_managed` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_live_recovery_a_then_fail_preserves_error` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_startup_recovery_a_interrupts` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_recovery_b_succeeds` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_idempotent_replay_and_no_partial_on_live_fail` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_final_remove_shutdown_before_empty_publication_cs` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_final_remove_shutdown_after_empty_publication_cs_completes` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_empty_recovery_a_missing_workspace_startup_and_live` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_empty_recovery_a_intent_and_committed_inconsistent` — `tiktoken artifacts not provisioned`

## `tests/unit/app/test_slice15d_product_ingest.py` — 32 skipped

- `tests/unit/app/test_slice15d_product_ingest.py::test_malformed_non_multipart_is_request_invalid` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_missing_corpus_multiple_corpus_zero_files` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_corpus_after_file_parts_succeeds` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_too_many_files_is_request_invalid` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_individual_file_over_limit_is_document_invalid` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_aggregate_file_bytes_over_limit_without_content_length` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_unsupported_source_is_document_invalid` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_filename_traversal_cannot_escape_storage` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_duplicate_filename_alone_is_allowed` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_conflicting_canonical_identity_fails_atomically` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_saturated_capacity_without_expensive_body` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_upload_interrupt_before_lease_cleans_staging` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_first_ingest_visibility_only_at_publication` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_published_n_visible_while_n1_building` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_stage_failure_leaves_published_n` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_publish_failure_before_pointer_leaves_n` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_successful_replace_matches_uploaded_set_exactly` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_repeated_identical_replacement_same_snapshot_id` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_dense_indexing_reuses_runtime_embedder_and_qdrant` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_health_responsive_during_blocking_scientific_stage` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_success_body_normative_contract_and_openapi` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_unexpected_path_field_rejected` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_corpus_busy_when_lease_held` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_client_filename_is_metadata_not_storage_name` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_invalid_corpus_first_aborts_before_file_spool` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_files_first_then_valid_corpus_still_succeeds` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_content_length_not_file_byte_bound` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_multipart_reorder_same_snapshot_id` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_typed_document_parse_error_is_document_invalid` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_unexpected_parser_exception_is_ingest_failed[<lambda>0]` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_unexpected_parser_exception_is_ingest_failed[<lambda>1]` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice15d_product_ingest.py::test_internal_ingestion_failure_is_ingest_failed` — `tiktoken artifacts not provisioned`

## `tests/unit/app/test_slice16k_b_ingestion_observability.py` — 21 skipped

- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_worklist_membership_immutable_after_first_write` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_successful_add_persists_bounded_metrics_and_worklist` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_mixed_valid_and_empty_ocr_pdf_add_fails_without_publication_change` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_dense_active_documents_follow_exact_batch_membership` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_idempotent_replay_keeps_single_worklist_identity` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_live_failure_preserves_observability_and_recovered_a` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r1_add_to_existing_separates_request_from_reconstruction` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r1_replace_request_metrics` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r1_remove_with_remaining_and_empty` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_worklist_durable_on_202_before_worker` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_forced_admission_freeze_failure_prevents_202` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_no_partial_admission_projection_on_freeze_failure` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_existing_nonterminal_missing_observability_is_repaired` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_api_freeze_fail_retry_launches_same_operation` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_preparing_missing_projection_fails_closed_no_admit` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_unrepairable_existing_reservation_fails_closed` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_idempotent_replay_with_frozen_worklist_unchanged` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r3_capacity_not_leaked_when_admission_freeze_fails` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r4a_live_failure_records_truthful_total_and_clears_activity` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r4a_startup_interrupted_does_not_fabricate_live_timing` — `tiktoken artifacts not provisioned`
- `tests/unit/app/test_slice16k_b_ingestion_observability.py::test_r4b_cache_reused_observation_does_not_perturb_execution` — `tiktoken artifacts not provisioned`
