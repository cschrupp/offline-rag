"""GoldDataset v1 models, loader, and semantic identity (Slice 9)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.core.ids import gold_dataset_id_from_payload
from offline_rag.domain.types import NonEmptyStr

GOLD_SCHEMA_V1 = "offline-rag-gold-v1"
LEGACY_SOURCE_SCHEMA = "legacy-binary"
LEGACY_COMPAT_MODE = "relevant_chunk_ids-to-grade-1"
RETRIEVAL_METRICS_V1 = "retrieval-metrics-v1"
RETRIEVAL_EVAL_RESULT_V1 = "offline-rag-retrieval-eval-result-v1"
RETRIEVAL_EVAL_COMPARISON_V1 = "offline-rag-retrieval-eval-comparison-v1"

CANONICAL_CUTOFFS: tuple[int, ...] = (1, 5, 10)
DIAGNOSTIC_HIT_RATE_CUTOFF = 30


class GoldDatasetError(ValueError):
    """Fail-closed GoldDataset validation/loading error."""


def _normalize_label(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise GoldDatasetError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise GoldDatasetError(f"{field_name} must be non-empty after trim")
    return text


class ChunkJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    relevance: Literal[1, 2]

    @field_validator("chunk_id")
    @classmethod
    def _chunk_id_strip(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("chunk_id must be non-empty")
        return text


class GoldCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonEmptyStr
    query: NonEmptyStr
    category: str | None = None
    tags: tuple[str, ...] = ()
    judgments: tuple[ChunkJudgment, ...] = ()

    @field_validator("query")
    @classmethod
    def _query_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be non-empty")
        return value

    @field_validator("category", mode="before")
    @classmethod
    def _category_normalize(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("category must be a string or null")
        text = value.strip()
        return text or None

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_normalize(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("tags must be a list of strings")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            label = _normalize_label(str(item), field_name="tag")
            if label in seen:
                raise ValueError(f"duplicate tag after normalization: {label}")
            seen.add(label)
            normalized.append(label)
        return tuple(normalized)

    @field_validator("judgments", mode="before")
    @classmethod
    def _judgments_tuple(cls, value: Any) -> Any:
        if value is None:
            return ()
        return value

    @model_validator(mode="after")
    def _unique_judgment_chunks(self) -> GoldCase:
        seen: set[str] = set()
        for judgment in self.judgments:
            if judgment.chunk_id in seen:
                raise ValueError(
                    f"duplicate judgment chunk_id within case {self.id}: {judgment.chunk_id}"
                )
            seen.add(judgment.chunk_id)
        return self

    @property
    def quality_eligible(self) -> bool:
        return len(self.judgments) > 0

    def positive_chunk_ids(self) -> set[str]:
        return {j.chunk_id for j in self.judgments}

    def relevance_map(self) -> dict[str, int]:
        return {j.chunk_id: int(j.relevance) for j in self.judgments}


class GoldDatasetMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GOLD_SCHEMA_V1
    chunk_set_id: NonEmptyStr
    corpus_id: NonEmptyStr | None = None
    corpus_name: NonEmptyStr | None = None
    dataset_id: NonEmptyStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedGoldDataset:
    meta: GoldDatasetMeta
    cases: tuple[GoldCase, ...]
    dataset_id: str
    source_schema: str
    compatibility_mode: str | None
    path: Path

    @property
    def quality_eligible_count(self) -> int:
        return sum(1 for case in self.cases if case.quality_eligible)


def gold_semantic_payload(
    *,
    chunk_set_id: str,
    corpus_id: str | None,
    corpus_name: str | None,
    cases: list[GoldCase] | tuple[GoldCase, ...],
) -> dict[str, Any]:
    """Build the canonical GoldDataset v1 semantic payload (Decision 11)."""
    corpus: dict[str, Any] = {}
    if corpus_id is not None:
        corpus["corpus_id"] = corpus_id
    if corpus_name is not None:
        corpus["corpus_name"] = corpus_name

    case_payloads: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda item: item.id):
        tags = sorted(case.tags)
        judgments = [
            {"chunk_id": j.chunk_id, "relevance": int(j.relevance)}
            for j in sorted(case.judgments, key=lambda item: item.chunk_id)
        ]
        case_payloads.append(
            {
                "id": case.id,
                "query": case.query,
                "category": case.category,
                "tags": tags,
                "judgments": judgments,
            }
        )
    return {
        "schema_version": GOLD_SCHEMA_V1,
        "chunk_set_id": chunk_set_id,
        "corpus": corpus,
        "cases": case_payloads,
    }


def compute_gold_dataset_id(
    *,
    chunk_set_id: str,
    corpus_id: str | None,
    corpus_name: str | None,
    cases: list[GoldCase] | tuple[GoldCase, ...],
) -> str:
    return gold_dataset_id_from_payload(
        gold_semantic_payload(
            chunk_set_id=chunk_set_id,
            corpus_id=corpus_id,
            corpus_name=corpus_name,
            cases=cases,
        )
    )


def _parse_native_case(raw: dict[str, Any], *, line_no: int) -> GoldCase:
    if "relevant_chunk_ids" in raw:
        raise GoldDatasetError(
            f"line {line_no}: offline-rag-gold-v1 cases must use judgments[], "
            "not relevant_chunk_ids"
        )
    if "judgments" not in raw:
        raise GoldDatasetError(f"line {line_no}: judgments is required for gold-v1")
    try:
        return GoldCase.model_validate(
            {
                "id": raw.get("id"),
                "query": raw.get("query"),
                "category": raw.get("category"),
                "tags": raw.get("tags") or [],
                "judgments": raw.get("judgments") or [],
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise GoldDatasetError(f"line {line_no}: invalid gold-v1 case: {exc}") from exc


def _parse_legacy_case(raw: dict[str, Any], *, line_no: int) -> GoldCase:
    # Known historical shape: id/query/relevant_chunk_ids (+ optional docs/metadata).
    if "judgments" in raw:
        raise GoldDatasetError(
            f"line {line_no}: legacy cases cannot mix judgments with relevant_chunk_ids"
        )
    case_id = raw.get("id")
    query = raw.get("query")
    chunk_ids = raw.get("relevant_chunk_ids")
    if not isinstance(chunk_ids, list):
        # Document-only legacy cases become quality-ineligible (empty judgments).
        chunk_ids = []
    judgments = [{"chunk_id": str(cid), "relevance": 1} for cid in chunk_ids]
    try:
        return GoldCase.model_validate(
            {
                "id": case_id,
                "query": query,
                "category": None,
                "tags": [],
                "judgments": judgments,
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise GoldDatasetError(f"line {line_no}: invalid legacy case: {exc}") from exc


def _looks_like_legacy_case(raw: dict[str, Any]) -> bool:
    return "relevant_chunk_ids" in raw or (
        "judgments" not in raw and ("query" in raw or "id" in raw)
    )


def load_gold_dataset(path: Path) -> LoadedGoldDataset:
    """Load GoldDataset v1 or legacy-compatible retrieval eval directory."""
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise GoldDatasetError(f"dataset not found: {dataset_path}")

    if dataset_path.is_dir():
        meta_path = dataset_path / "meta.json"
        cases_path = dataset_path / "cases.jsonl"
    elif dataset_path.suffix == ".jsonl":
        meta_path = dataset_path.with_name("meta.json")
        cases_path = dataset_path
        dataset_path = dataset_path.parent
    else:
        raise GoldDatasetError("dataset must be a directory with meta.json + cases.jsonl")

    if not meta_path.exists():
        raise GoldDatasetError(f"dataset metadata missing: {meta_path}")
    if not cases_path.exists():
        raise GoldDatasetError(f"dataset cases missing: {cases_path}")

    try:
        raw_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GoldDatasetError(f"invalid meta.json: {exc}") from exc
    if not isinstance(raw_meta, dict):
        raise GoldDatasetError("meta.json must be an object")

    schema_version = raw_meta.get("schema_version")
    native = schema_version == GOLD_SCHEMA_V1
    legacy = schema_version in (None, 1, "1") and not native

    if native:
        try:
            meta = GoldDatasetMeta.model_validate(raw_meta)
        except Exception as exc:  # noqa: BLE001
            raise GoldDatasetError(f"invalid gold-v1 meta: {exc}") from exc
        source_schema = GOLD_SCHEMA_V1
        compatibility_mode = None
    elif legacy:
        # Historical integer schema_version=1 meta.
        chunk_set_id = raw_meta.get("chunk_set_id")
        if not chunk_set_id or not str(chunk_set_id).strip():
            raise GoldDatasetError("legacy meta.json requires chunk_set_id")
        meta = GoldDatasetMeta(
            schema_version=GOLD_SCHEMA_V1,
            chunk_set_id=str(chunk_set_id),
            corpus_id=raw_meta.get("corpus_id"),
            corpus_name=(raw_meta.get("metadata") or {}).get("corpus_name")
            if isinstance(raw_meta.get("metadata"), dict)
            else None,
            dataset_id=None,
            metadata=dict(raw_meta.get("metadata") or {}),
        )
        source_schema = LEGACY_SOURCE_SCHEMA
        compatibility_mode = LEGACY_COMPAT_MODE
    else:
        raise GoldDatasetError(
            f"unsupported gold schema_version: {schema_version!r}; "
            f"expected {GOLD_SCHEMA_V1!r} or legacy schema_version=1"
        )

    cases: list[GoldCase] = []
    seen_ids: set[str] = set()
    for line_no, line in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldDatasetError(f"line {line_no}: invalid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise GoldDatasetError(f"line {line_no}: case must be a JSON object")

        if native:
            case = _parse_native_case(raw, line_no=line_no)
        else:
            if not _looks_like_legacy_case(raw):
                raise GoldDatasetError(
                    f"line {line_no}: unrecognized legacy case shape"
                )
            case = _parse_legacy_case(raw, line_no=line_no)

        if case.id in seen_ids:
            raise GoldDatasetError(f"duplicate case id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise GoldDatasetError("dataset contains no cases")

    dataset_id = compute_gold_dataset_id(
        chunk_set_id=meta.chunk_set_id,
        corpus_id=meta.corpus_id,
        corpus_name=meta.corpus_name,
        cases=cases,
    )
    if meta.dataset_id is not None and meta.dataset_id != dataset_id:
        raise GoldDatasetError(
            f"persisted dataset_id mismatch: meta has {meta.dataset_id}, "
            f"canonical recomputation yields {dataset_id}"
        )

    return LoadedGoldDataset(
        meta=meta.model_copy(update={"dataset_id": dataset_id}),
        cases=tuple(cases),
        dataset_id=dataset_id,
        source_schema=source_schema,
        compatibility_mode=compatibility_mode,
        path=dataset_path,
    )
