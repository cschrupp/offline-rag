"""Product application boundary (Slice 15).

Adapters (CLI, FastAPI) call into this package. Domain algorithms remain in
their existing packages; this layer owns use-case contracts, errors, and
application lifecycle helpers authorized for the current phase.
"""

from offline_rag.app.candidate_recovery import recover_abandoned_candidates
from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import (
    ERROR_CATALOG,
    AppError,
    ErrorCode,
    ErrorResponse,
    SafeErrorDetails,
    ValidationFieldDetail,
    error_response_from_app_error,
    http_status_for,
    retryable_for,
    sanitize_error_details,
)
from offline_rag.app.leases import CorpusMutationLease, corpus_lease_path
from offline_rag.app.paths import ensure_data_directories, required_data_directories
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ConstructionCounters,
    ProcessResources,
    ResourceFactories,
    RuntimeState,
    default_resource_factories,
)
from offline_rag.app.snapshot import (
    PRODUCT_MODE_GROUNDED_V1,
    CanonicalSnapshotManifest,
    CorpusReadSnapshot,
    compute_snapshot_id,
)
from offline_rag.app.startup_validation import validate_global_startup_requirements
from offline_rag.app.validation import (
    app_error_from_validation_errors,
    project_validation_errors,
)

__all__ = [
    "ERROR_CATALOG",
    "PRODUCT_MODE_GROUNDED_V1",
    "AppError",
    "ApplicationRuntime",
    "CanonicalSnapshotManifest",
    "ConstructionCounters",
    "CorpusMutationLease",
    "CorpusReadSnapshot",
    "ErrorCode",
    "ErrorResponse",
    "ProcessResources",
    "ProductPublicationRegistry",
    "ResourceFactories",
    "RuntimeState",
    "SafeErrorDetails",
    "ValidationFieldDetail",
    "app_error_from_validation_errors",
    "compute_snapshot_id",
    "corpus_lease_path",
    "default_resource_factories",
    "ensure_data_directories",
    "error_response_from_app_error",
    "http_status_for",
    "project_validation_errors",
    "recover_abandoned_candidates",
    "required_data_directories",
    "retryable_for",
    "sanitize_error_details",
    "validate_global_startup_requirements",
    "validate_product_corpus_name",
]
