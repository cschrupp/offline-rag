"""Project-owned durable inverted index for lexical retrieval."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from offline_rag.core.ids import (
    BM25_OKAPI_CONTRACT,
    LOCAL_INVERTED_INDEX_CONTRACT,
    TECHNICAL_ANALYZER_CONTRACT,
)
from offline_rag.lexical.scoring import BM25OkapiV1Scorer

METADATA_NAME = "metadata.json"
DOCUMENTS_NAME = "documents.json"
POSTINGS_NAME = "postings.json"
SCHEMA_VERSION = "offline-rag-local-inverted-index-v1"


@dataclass(frozen=True)
class LexicalDocumentInput:
    """One analyzed child ready for inverted-index materialization."""

    chunk_id: str
    terms: list[str]
    chunk_artifact_id: str | None = None
    document_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LexicalSearchHit:
    """Backend-agnostic lexical search hit (no storage types)."""

    chunk_id: str
    score: float
    chunk_artifact_id: str | None = None
    document_id: str | None = None
    doc_id: int | None = None


class LexicalIndexBackend(Protocol):
    """Minimal inverted-index adapter for lexical indexing and retrieval."""

    def index_exists(self, lexical_index_id: str) -> bool:
        """Return whether a published index directory exists."""

    def build(
        self,
        lexical_index_id: str,
        documents: list[LexicalDocumentInput],
        *,
        chunk_set_id: str,
        lexical_config_hash: str,
        k1: float = 1.2,
        b: float = 0.75,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Materialize a complete immutable index and return metadata."""

    def open(self, lexical_index_id: str) -> None:
        """Load a published index into memory for search."""

    def search(self, query_terms: list[str], *, top_k: int) -> list[LexicalSearchHit]:
        """Return ranked hits for unique analyzed query terms."""

    def validate(self, lexical_index_id: str) -> bool:
        """Return whether the published index passes integrity checks."""

    def metadata(self) -> dict[str, Any]:
        """Return loaded index metadata (requires open)."""

    def close(self) -> None:
        """Release in-memory state."""


def _canonical_json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _canonical_json_dumps(payload)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def index_dir(root: Path, lexical_index_id: str) -> Path:
    return Path(root) / lexical_index_id


class LocalInvertedIndexBackend:
    """JSON-backed inverted index under ``data/lexical-indexes/<id>/``."""

    backend = "local_inverted"
    backend_contract = LOCAL_INVERTED_INDEX_CONTRACT

    def __init__(
        self,
        root: Path,
        *,
        scorer: BM25OkapiV1Scorer | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._scorer = scorer or BM25OkapiV1Scorer()
        self._lexical_index_id: str | None = None
        self._metadata: dict[str, Any] | None = None
        self._documents: list[dict[str, Any]] = []
        self._doc_by_chunk: dict[str, dict[str, Any]] = {}
        self._postings: dict[str, dict[str, Any]] = {}
        self._doc_lengths: dict[str, float] = {}

    def index_exists(self, lexical_index_id: str) -> bool:
        path = index_dir(self.root, lexical_index_id)
        return (
            path.is_dir()
            and (path / METADATA_NAME).exists()
            and (path / DOCUMENTS_NAME).exists()
            and (path / POSTINGS_NAME).exists()
        )

    def build(
        self,
        lexical_index_id: str,
        documents: list[LexicalDocumentInput],
        *,
        chunk_set_id: str,
        lexical_config_hash: str,
        k1: float = 1.2,
        b: float = 0.75,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.index_exists(lexical_index_id):
            if not self.validate(lexical_index_id):
                raise RuntimeError(f"existing lexical index failed validation: {lexical_index_id}")
            meta_path = index_dir(self.root, lexical_index_id) / METADATA_NAME
            return json.loads(meta_path.read_text(encoding="utf-8"))

        if not documents:
            raise ValueError("cannot build lexical index with zero documents")

        ordered = sorted(documents, key=lambda item: item.chunk_id)
        chunk_ids = [item.chunk_id for item in ordered]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("duplicate chunk_id in lexical document inputs")

        doc_rows: list[dict[str, Any]] = []
        postings_map: dict[str, list[tuple[str, int]]] = defaultdict(list)
        total_tokens = 0

        for doc_id, item in enumerate(ordered):
            if not item.terms:
                raise ValueError(f"zero-term child cannot be indexed: {item.chunk_id}")
            counts = Counter(item.terms)
            length = sum(counts.values())
            if length < 1:
                raise ValueError(f"zero-term child cannot be indexed: {item.chunk_id}")
            total_tokens += length
            row: dict[str, Any] = {
                "chunk_id": item.chunk_id,
                "doc_id": doc_id,
                "length": length,
            }
            if item.chunk_artifact_id is not None:
                row["chunk_artifact_id"] = item.chunk_artifact_id
            if item.document_id is not None:
                row["document_id"] = item.document_id
            doc_rows.append(row)
            for term, tf in sorted(counts.items()):
                if tf < 1:
                    raise ValueError(f"invalid tf for {item.chunk_id}/{term}")
                postings_map[term].append((item.chunk_id, int(tf)))

        n = len(doc_rows)
        avgdl = float(total_tokens) / float(n)
        postings_payload: dict[str, Any] = {}
        for term in sorted(postings_map):
            pairs = sorted(postings_map[term], key=lambda pair: pair[0])
            # No duplicate (term, child) postings by construction (Counter).
            postings_payload[term] = {
                "df": len(pairs),
                "postings": [[chunk_id, tf] for chunk_id, tf in pairs],
            }

        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "lexical_index_id": lexical_index_id,
            "chunk_set_id": chunk_set_id,
            "lexical_config_hash": lexical_config_hash,
            "backend": self.backend,
            "backend_contract": self.backend_contract,
            "analyzer_contract": TECHNICAL_ANALYZER_CONTRACT,
            "bm25_contract": BM25_OKAPI_CONTRACT,
            "k1": float(k1),
            "b": float(b),
            "N": n,
            "avgdl": avgdl,
            "total_tokens": total_tokens,
            "vocabulary_size": len(postings_payload),
            "indexed_child_count": n,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        staging = self.root / f".building-{uuid.uuid4().hex}"
        final = index_dir(self.root, lexical_index_id)
        staging.mkdir(parents=True, exist_ok=False)
        try:
            _atomic_write_json(staging / DOCUMENTS_NAME, doc_rows)
            _atomic_write_json(staging / POSTINGS_NAME, postings_payload)
            _atomic_write_json(staging / METADATA_NAME, metadata)
            self._validate_payloads(metadata, doc_rows, postings_payload)
            if final.exists():
                raise RuntimeError(f"lexical index destination already exists: {final}")
            staging.replace(final)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        return metadata

    def open(self, lexical_index_id: str) -> None:
        if not self.validate(lexical_index_id):
            raise RuntimeError(f"lexical index failed validation: {lexical_index_id}")
        path = index_dir(self.root, lexical_index_id)
        metadata = json.loads((path / METADATA_NAME).read_text(encoding="utf-8"))
        documents = json.loads((path / DOCUMENTS_NAME).read_text(encoding="utf-8"))
        postings = json.loads((path / POSTINGS_NAME).read_text(encoding="utf-8"))
        self._lexical_index_id = lexical_index_id
        self._metadata = metadata
        self._documents = documents
        self._doc_by_chunk = {row["chunk_id"]: row for row in documents}
        self._postings = postings
        self._doc_lengths = {row["chunk_id"]: float(row["length"]) for row in documents}
        self._scorer = BM25OkapiV1Scorer(
            k1=float(metadata.get("k1", 1.2)),
            b=float(metadata.get("b", 0.75)),
        )

    def search(self, query_terms: list[str], *, top_k: int) -> list[LexicalSearchHit]:
        if self._metadata is None:
            raise RuntimeError("lexical index is not open")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if not query_terms:
            return []

        n = int(self._metadata["N"])
        avgdl = float(self._metadata["avgdl"])
        dfs = {term: int(payload["df"]) for term, payload in self._postings.items()}
        postings_by_term: dict[str, list[tuple[str, float]]] = {
            term: [(str(chunk_id), float(tf)) for chunk_id, tf in payload["postings"]]
            for term, payload in self._postings.items()
        }
        scores = self._scorer.accumulate(
            query_terms=query_terms,
            postings_by_term=postings_by_term,
            doc_lengths=self._doc_lengths,
            avgdl=avgdl,
            n=n,
            dfs=dfs,
        )
        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        hits: list[LexicalSearchHit] = []
        for chunk_id, score in ranked:
            row = self._doc_by_chunk[chunk_id]
            hits.append(
                LexicalSearchHit(
                    chunk_id=chunk_id,
                    score=float(score),
                    chunk_artifact_id=row.get("chunk_artifact_id"),
                    document_id=row.get("document_id"),
                    doc_id=int(row["doc_id"]),
                )
            )
        return hits

    def validate(self, lexical_index_id: str) -> bool:
        path = index_dir(self.root, lexical_index_id)
        try:
            if not path.is_dir():
                return False
            metadata = json.loads((path / METADATA_NAME).read_text(encoding="utf-8"))
            documents = json.loads((path / DOCUMENTS_NAME).read_text(encoding="utf-8"))
            postings = json.loads((path / POSTINGS_NAME).read_text(encoding="utf-8"))
            self._validate_payloads(metadata, documents, postings)
            return metadata.get("lexical_index_id") == lexical_index_id
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return False

    def metadata(self) -> dict[str, Any]:
        if self._metadata is None:
            raise RuntimeError("lexical index is not open")
        return dict(self._metadata)

    @property
    def n(self) -> int:
        if self._metadata is None:
            raise RuntimeError("lexical index is not open")
        return int(self._metadata["N"])

    def term_info(self, term: str) -> dict[str, Any] | None:
        if self._metadata is None:
            raise RuntimeError("lexical index is not open")
        payload = self._postings.get(term)
        if payload is None:
            return None
        postings = [(str(chunk_id), int(tf)) for chunk_id, tf in payload["postings"]]
        return {"df": int(payload["df"]), "postings": postings}

    def document_info(self, chunk_id: str) -> dict[str, Any] | None:
        if self._metadata is None:
            raise RuntimeError("lexical index is not open")
        row = self._doc_by_chunk.get(chunk_id)
        return dict(row) if row is not None else None

    def close(self) -> None:
        self._lexical_index_id = None
        self._metadata = None
        self._documents = []
        self._doc_by_chunk = {}
        self._postings = {}
        self._doc_lengths = {}

    def _validate_payloads(
        self,
        metadata: dict[str, Any],
        documents: list[dict[str, Any]],
        postings: dict[str, Any],
    ) -> None:
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported lexical index schema_version")
        if metadata.get("backend_contract") != LOCAL_INVERTED_INDEX_CONTRACT:
            raise ValueError("backend_contract mismatch")
        n = int(metadata["N"])
        if n != len(documents):
            raise ValueError("N does not match documents length")
        if int(metadata["indexed_child_count"]) != n:
            raise ValueError("indexed_child_count mismatch")
        if n < 1:
            raise ValueError("lexical index must contain at least one document")

        chunk_ids = [str(row["chunk_id"]) for row in documents]
        if chunk_ids != sorted(chunk_ids):
            raise ValueError("documents.json must be sorted by chunk_id")
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("duplicate chunk_id in documents.json")

        total_tokens = 0
        for expected_doc_id, row in enumerate(documents):
            if int(row["doc_id"]) != expected_doc_id:
                raise ValueError("doc_id assignment must be 0..n-1 by sorted chunk_id")
            length = int(row["length"])
            if length < 1:
                raise ValueError(f"document length must be >= 1 for {row['chunk_id']}")
            total_tokens += length

        avgdl = float(metadata["avgdl"])
        expected_avgdl = float(total_tokens) / float(n)
        if abs(avgdl - expected_avgdl) > 1e-9:
            raise ValueError("avgdl does not match sum(dl)/N")
        if int(metadata.get("total_tokens", total_tokens)) != total_tokens:
            raise ValueError("total_tokens mismatch")
        if int(metadata["vocabulary_size"]) != len(postings):
            raise ValueError("vocabulary_size mismatch")

        known = set(chunk_ids)
        for term, payload in postings.items():
            pairs = payload["postings"]
            df = int(payload["df"])
            if df != len(pairs):
                raise ValueError(f"df mismatch for term {term}")
            seen_chunks: set[str] = set()
            prev_chunk: str | None = None
            for chunk_id, tf in pairs:
                chunk_id = str(chunk_id)
                if chunk_id not in known:
                    raise ValueError(f"posting references unknown chunk_id {chunk_id}")
                if int(tf) < 1:
                    raise ValueError(f"tf must be >= 1 for {term}/{chunk_id}")
                if chunk_id in seen_chunks:
                    raise ValueError(f"duplicate posting for {term}/{chunk_id}")
                seen_chunks.add(chunk_id)
                if prev_chunk is not None and chunk_id < prev_chunk:
                    raise ValueError(f"postings for {term} must be sorted by chunk_id")
                prev_chunk = chunk_id
