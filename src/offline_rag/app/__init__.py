"""Product application boundary (Slice 15).

Adapters (CLI, FastAPI) call into this package. Domain algorithms remain in
their existing packages; this layer owns use-case contracts, errors, and
application lifecycle helpers authorized for the current phase.
"""

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import (
    ERROR_CATALOG,
    AppError,
    ErrorCode,
    ErrorResponse,
    error_response_from_app_error,
    http_status_for,
    retryable_for,
    sanitize_error_details,
)
from offline_rag.app.paths import ensure_data_directories, required_data_directories
from offline_rag.app.validation import (
    app_error_from_validation_errors,
    project_validation_errors,
)

__all__ = [
    "ERROR_CATALOG",
    "AppError",
    "ErrorCode",
    "ErrorResponse",
    "app_error_from_validation_errors",
    "ensure_data_directories",
    "error_response_from_app_error",
    "http_status_for",
    "project_validation_errors",
    "required_data_directories",
    "retryable_for",
    "sanitize_error_details",
    "validate_product_corpus_name",
]
