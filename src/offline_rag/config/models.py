"""Application settings models validated with Pydantic v2.

Unknown keys are rejected. These settings describe runtime/application
configuration and remain separate from domain ``ExperimentConfig``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.core.ids import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_PINNED_REVISION,
    CHUNK_ID_ASC_TIE_BREAK,
    CONTEXT_STRATEGIES,
    PLAIN_PAIR_INPUT_CONTRACT,
    RAW_LOGIT_SCORE_CONTRACT,
    SENTENCE_TRANSFORMERS_CROSS_ENCODER_ADAPTER,
    SEQ_TRUNC_1024_PASSAGE_RIGHT,
)
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
    lexical_indexes: Path = Path("data/lexical-indexes")
    lexical_index_manifests: Path = Path("data/lexical-index-manifests")
    qdrant_storage: Path = Path("data/qdrant")
    retrieval_models: Path = Path("models")
    docling_artifacts: Path = Path("models/docling")
    tokenizer_artifacts: Path = Path("models/tokenizers/tiktoken")
    embedding_artifacts: Path = Path("models/embeddings")
    reranker_artifacts: Path = Path("models/rerankers")
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


class LexicalTextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: NonEmptyStr = "plain"
    contract_version: NonEmptyStr = "plain-v1"


class LexicalAnalyzerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: NonEmptyStr = "technical"
    contract_version: NonEmptyStr = "technical-v1"
    unicode_normalization: NonEmptyStr = "NFKC"
    case_normalization: NonEmptyStr = "casefold"
    stopwords: NonEmptyStr = "none"
    stemming: NonEmptyStr = "none"
    lemmatization: NonEmptyStr = "none"


class LexicalBm25Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: NonEmptyStr = "bm25-okapi-v1"
    k1: Score = 1.2
    b: Score = 0.75
    idf: NonEmptyStr = "rsj-positive-smoothed-v1"
    query_tf: NonEmptyStr = "unique-terms-v1"

    @field_validator("k1", "b")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("BM25 parameters must be >= 0")
        return value


class LexicalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    method: NonEmptyStr = "bm25"
    top_k: PositiveInt = 30
    backend: NonEmptyStr = "local_inverted"
    backend_contract: NonEmptyStr = "local-inverted-index-v1"
    text: LexicalTextSettings = Field(default_factory=LexicalTextSettings)
    analyzer: LexicalAnalyzerSettings = Field(default_factory=LexicalAnalyzerSettings)
    bm25: LexicalBm25Settings = Field(default_factory=LexicalBm25Settings)


class FusionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: NonEmptyStr = "rrf"
    contract_version: NonEmptyStr = "rrf-v1"
    rrf_k: PositiveInt = 60
    dense_top_k: PositiveInt = 30
    lexical_top_k: PositiveInt = 30
    output_top_k: PositiveInt = 10


class RerankerModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: NonEmptyStr = BGE_RERANKER_MODEL_ID
    revision: NonEmptyStr = BGE_RERANKER_PINNED_REVISION
    model_path: Path = Path("models/rerankers/bge-reranker-v2-m3")
    adapter_contract: NonEmptyStr = SENTENCE_TRANSFORMERS_CROSS_ENCODER_ADAPTER
    local_files_only: bool = True
    trust_remote_code: bool = False


class RerankerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    implementation: NonEmptyStr = "sentence_transformers"
    model: RerankerModelSettings = Field(default_factory=RerankerModelSettings)
    input_k: PositiveInt = 30
    output_k: PositiveInt = 10
    input_construction: NonEmptyStr = PLAIN_PAIR_INPUT_CONTRACT
    sequence_contract: NonEmptyStr = SEQ_TRUNC_1024_PASSAGE_RIGHT
    max_length: PositiveInt = 1024
    score_transform: NonEmptyStr = RAW_LOGIT_SCORE_CONTRACT
    tie_break: NonEmptyStr = CHUNK_ID_ASC_TIE_BREAK
    device: NonEmptyStr = "auto"
    batch_size: PositiveInt = 16

    @model_validator(mode="after")
    def _validate_sequence_contract(self) -> RerankerSettings:
        if self.sequence_contract == SEQ_TRUNC_1024_PASSAGE_RIGHT and self.max_length != 1024:
            raise ValueError(
                f"{SEQ_TRUNC_1024_PASSAGE_RIGHT} requires max_length=1024 "
                f"(got {self.max_length})"
            )
        if not self.model.local_files_only:
            raise ValueError("reranker.model.local_files_only must be true")
        if self.model.trust_remote_code:
            raise ValueError("reranker.model.trust_remote_code must be false")
        return self


class ContextSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    strategy: NonEmptyStr = "parent"
    anchor_k: PositiveInt = 5
    max_context_tokens: PositiveInt = 6000
    neighbor_window: NonNegativeInt = 0

    @model_validator(mode="after")
    def _validate_context_policy(self) -> ContextSettings:
        if self.strategy not in CONTEXT_STRATEGIES:
            allowed = ", ".join(sorted(CONTEXT_STRATEGIES))
            raise ValueError(f"context.strategy must be one of: {allowed}")
        if self.strategy in {"child-only", "parent"} and self.neighbor_window != 0:
            raise ValueError(
                f"context.strategy={self.strategy} requires neighbor_window=0 "
                f"(got {self.neighbor_window})"
            )
        if self.strategy in {"neighbors", "parent+neighbors"} and self.neighbor_window < 1:
            raise ValueError(
                f"context.strategy={self.strategy} requires neighbor_window>=1 "
                f"(got {self.neighbor_window})"
            )
        return self


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
    lexical: LexicalSettings = Field(default_factory=LexicalSettings)
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
