"""Application settings models validated with Pydantic v2.

Unknown keys are rejected. These settings describe runtime/application
configuration and remain separate from domain ``ExperimentConfig``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt, Score


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr = "offline-rag"
    strict_offline: bool = True


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_data: Path = Path("data/raw")
    manifests: Path = Path("data/manifests")
    processed: Path = Path("data/processed")
    corpora: Path = Path("data/corpora")
    chunks: Path = Path("data/chunks")
    chunk_manifests: Path = Path("data/chunk-manifests")
    embeddings: Path = Path("data/embeddings")
    index_manifests: Path = Path("data/index-manifests")
    qdrant_storage: Path = Path("data/qdrant")
    retrieval_models: Path = Path("models")
    docling_artifacts: Path = Path("models/docling")
    tokenizer_artifacts: Path = Path("models/tokenizers/tiktoken")
    embedding_artifacts: Path = Path("models/embeddings")
    eval_results: Path = Path("eval/results")


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    structured: bool = True


class DeploymentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: NonEmptyStr = "standalone_ollama"
    qdrant_mode: NonEmptyStr = "local"


class PdfParsingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ocr_enabled: bool = False


class ParsingSettings(BaseModel):
    """Parse-relevant settings that participate in parse_config_hash."""

    model_config = ConfigDict(extra="forbid")

    pdf: PdfParsingSettings = Field(default_factory=PdfParsingSettings)


class TokenizerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    implementation: NonEmptyStr = "tiktoken"
    encoding: NonEmptyStr = "cl100k_base"


class ChildChunkingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_tokens: PositiveInt = 350
    max_tokens: PositiveInt = 512


class ParentChunkingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_tokens: PositiveInt = 1200
    max_tokens: PositiveInt = 2000


class ChunkingSettings(BaseModel):
    """Parse-independent chunking settings that participate in chunk_config_hash."""

    model_config = ConfigDict(extra="forbid")

    strategy: NonEmptyStr = "structure_aware"
    parent_child: bool = True
    tokenizer: TokenizerSettings = Field(default_factory=TokenizerSettings)
    child: ChildChunkingSettings = Field(default_factory=ChildChunkingSettings)
    parent: ParentChunkingSettings = Field(default_factory=ParentChunkingSettings)


class IngestionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser: NonEmptyStr = "docling"
    chunker: NonEmptyStr = "docling_hybrid"
    target_tokens: PositiveInt = 384
    max_tokens: PositiveInt = 512
    preserve_tables: bool = True
    parent_child: bool = True


class DenseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model: NonEmptyStr = "Qwen/Qwen3-Embedding-0.6B"
    model_path: Path = Path("models/embeddings/qwen3-embedding-0.6b")
    local_files_only: bool = True
    top_k: PositiveInt = 10


class EmbeddingTextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: NonEmptyStr = "plain"
    contract_version: NonEmptyStr = "plain-v1"


class EmbeddingModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    implementation: NonEmptyStr = "sentence_transformers"
    model_id: NonEmptyStr = "Qwen/Qwen3-Embedding-0.6B"
    revision: NonEmptyStr = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    dimension: PositiveInt = 1024
    normalize: bool = True
    adapter_contract: NonEmptyStr = "sentence-transformers-v1"
    batch_size: PositiveInt = 32
    device: NonEmptyStr = "cpu"
    query_instruction: str | None = None
    document_instruction: str | None = None


class IndexingSettings(BaseModel):
    """Dense indexing settings that participate in embedding/index hashes."""

    model_config = ConfigDict(extra="forbid")

    backend: NonEmptyStr = "qdrant_local"
    backend_contract: NonEmptyStr = "qdrant-local-v1"
    metric: NonEmptyStr = "cosine"
    embedding_text: EmbeddingTextSettings = Field(default_factory=EmbeddingTextSettings)
    embedding: EmbeddingModelSettings = Field(default_factory=EmbeddingModelSettings)


class SparseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    method: NonEmptyStr = "bm25"
    top_k: PositiveInt = 30


class FusionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: NonEmptyStr = "rrf"
    rrf_k: PositiveInt = 60


class RerankerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model: NonEmptyStr = "REPLACE_WITH_LOCAL_RERANKER"
    model_path: Path = Path("models/reranker/REPLACE_ME")
    local_files_only: bool = True
    input_k: PositiveInt = 30
    output_k: PositiveInt = 6


class ContextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: NonEmptyStr = "parent"
    max_context_tokens: PositiveInt = 6000
    neighbor_window: NonNegativeInt = 0


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: NonEmptyStr = "openai_compatible"
    base_url: NonEmptyStr = "http://127.0.0.1:11434/v1"
    model: NonEmptyStr = "REPLACE_WITH_APPROVED_LOCAL_MODEL"
    temperature: Score = 0.0
    max_output_tokens: PositiveInt = 1200
    timeout_seconds: PositiveInt = 120
    approved_endpoints: list[NonEmptyStr] = Field(
        default_factory=lambda: ["http://127.0.0.1:11434/v1"]
    )
    approved_models: list[str] = Field(default_factory=list)

    @field_validator("temperature")
    @classmethod
    def _temperature_range(cls, value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return value


class RetrievalRecoverySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_retries: NonNegativeInt = 1


class AbstentionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    policy: NonEmptyStr = "score_threshold"
    threshold: Score | None = None


class SecuritySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    treat_documents_as_untrusted: bool = True
    allow_network_tools: bool = False
    allow_shell_tools: bool = False
    allow_arbitrary_filesystem_tools: bool = False
    validate_citations: bool = True
    reject_unapproved_generation_endpoint: bool = True
    reject_unapproved_generation_model: bool = True


class ExperimentSection(BaseModel):
    """Optional experiment label section found in experiment YAML overlays."""

    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr


class AppSettings(BaseModel):
    """Validated application settings loaded by the config loader."""

    model_config = ConfigDict(extra="forbid")

    project: ProjectSettings = Field(default_factory=ProjectSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    deployment: DeploymentSettings = Field(default_factory=DeploymentSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    parsing: ParsingSettings = Field(default_factory=ParsingSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    indexing: IndexingSettings = Field(default_factory=IndexingSettings)
    dense: DenseSettings = Field(default_factory=DenseSettings)
    sparse: SparseSettings = Field(default_factory=SparseSettings)
    fusion: FusionSettings = Field(default_factory=FusionSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    retrieval_recovery: RetrievalRecoverySettings = Field(default_factory=RetrievalRecoverySettings)
    abstention: AbstentionSettings = Field(default_factory=AbstentionSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    experiment: ExperimentSection | None = None

    def to_canonical_dict(self) -> dict[str, Any]:
        """JSON-ready mapping suitable for deterministic config hashing."""
        return self.model_dump(mode="json")
