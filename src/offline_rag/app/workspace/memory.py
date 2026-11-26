"""Local workspace learning records and bounded topic recall."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings

SemanticEmbed = Callable[[Sequence[str]], list[list[float]]]
logger = logging.getLogger(__name__)


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0.0


Category = Literal["episode", "semantic", "learning", "derived"]
MAX_TEXT = 6000
MAX_REVISIONS = 20
RECALL_LIMIT = 24
SEMANTIC_RECALL_MIN_COSINE = 0.75
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "can",
        "could",
        "describe",
        "do",
        "does",
        "explain",
        "for",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "please",
        "tell",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "would",
        "you",
        "about",
        "more",
        "summarize",
        "give",
        "mean",
        "know",
    ]
)


# Only explicit domain equivalents and unambiguous question templates.
_TOPIC_ALIASES = re.compile(r"\bself[ -]+contained breathing apparatus\b")
_TOOL_QUESTION = re.compile(
    r"^what tools (?:are used|do (?:i|you) use) for (.+?)[?.]*$"
)


def _terms(value: str) -> tuple[str, ...]:
    normalized = _TOPIC_ALIASES.sub("scba", value.casefold()[:MAX_TEXT])
    return tuple(
        dict.fromkeys(
            term
            for term in re.findall(r"[^\W_]+", normalized)
            if term not in STOP_WORDS
        )
    )


_TOPIC_OPENING = re.compile(
    r"^(?:what is|explain|describe|define|tell me about|give me an overview of)\s+"
)


def topic_label(value: str) -> str:
    """Keep topic word order while removing recognized request framing."""
    question = value.strip().casefold()
    tools = _TOOL_QUESTION.fullmatch(question)
    if tools:
        return tools.group(1).strip(" ?.!")[:120]
    return _TOPIC_OPENING.sub("", question).strip(" ?.!")[:120]


def topic_terms(value: str) -> tuple[str, ...]:
    """Extract a bounded topic, including known question templates."""
    question = value.strip().casefold()
    tools = _TOOL_QUESTION.fullmatch(question)
    return _terms(tools.group(1) if tools else _TOPIC_OPENING.sub("", question))[:12]


class WorkspaceMemory:
    """Store records under the owning workspace without altering publications."""

    def __init__(self, settings: AppSettings, workspace_id: str) -> None:
        self.workspace = WorkspaceStore(settings)
        self.workspace_id = workspace_id
        self.path = self.workspace.workspace_dir(workspace_id) / "knowledge.sqlite3"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        connection = sqlite3.connect(self.path, timeout=0.15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                connection.execute("PRAGMA secure_delete = ON")
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS settings (enabled INTEGER NOT NULL)"
                )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS records (
                        id TEXT PRIMARY KEY, category TEXT NOT NULL, origin TEXT NOT NULL,
                        topic TEXT NOT NULL, terms TEXT NOT NULL, text TEXT NOT NULL,
                        revision INTEGER NOT NULL, created_at TEXT NOT NULL,
                        provenance TEXT NOT NULL, history TEXT NOT NULL,
                        parent_id TEXT REFERENCES records(id) ON DELETE CASCADE,
                        relation TEXT
                    )
                """)
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS records_recent ON records(created_at DESC, id)"
                )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS record_terms (
                        term TEXT NOT NULL, id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (term, created_at DESC, id)
                    )
                """)
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS record_terms_by_id ON record_terms(id)"
                )
                if not connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'processed_operations'"
                ).fetchone():
                    connection.execute(
                        "CREATE TABLE processed_operations (kind TEXT NOT NULL, identity TEXT NOT NULL, PRIMARY KEY (kind, identity))"
                    )
                    connection.execute("""
                        INSERT INTO processed_operations SELECT 'capture', id
                        FROM records WHERE category = 'episode'
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS study_aids (
                        title_key TEXT NOT NULL, id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                        PRIMARY KEY (title_key, id)
                    )
                """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS study_inputs (
                        parent_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                        aid_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
                        PRIMARY KEY (parent_id, aid_id)
                    )
                """)
                connection.execute("""
                    CREATE TRIGGER IF NOT EXISTS forget_study_dependents BEFORE DELETE ON records
                    BEGIN
                        DELETE FROM records WHERE id IN (
                            SELECT aid_id FROM study_inputs WHERE parent_id = OLD.id
                        );
                    END
                """)
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS records_parent ON records(parent_id)"
                )
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _enabled(connection: sqlite3.Connection) -> bool:
        row = connection.execute("SELECT enabled FROM settings").fetchone()
        return row is not None and bool(row["enabled"])

    def set_enabled(self, enabled: bool) -> None:
        self.workspace.get(self.workspace_id)
        if not self.path.exists() and not enabled:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM settings")
            connection.execute("INSERT INTO settings VALUES (?)", (enabled,))

    def is_enabled(self) -> bool:
        self.workspace.get(self.workspace_id)
        if not self.path.is_file():
            return False
        with self._connect() as connection:
            return self._enabled(connection)

    @staticmethod
    def _claim_operation(
        connection: sqlite3.Connection, kind: str, identity: str
    ) -> bool:
        return (
            connection.execute(
                "INSERT OR IGNORE INTO processed_operations VALUES (?, ?)",
                (kind, identity),
            ).rowcount
            == 1
        )

    def capture(
        self,
        *,
        event_id: str,
        question: str,
        topic_question: str,
        answer: str,
        provenance: dict[str, Any],
        require_enabled: bool = False,
    ) -> None:
        """Organize an already committed cited discussion once."""
        if not self.path.is_file():
            return
        terms = topic_terms(topic_question)
        if not terms:
            return
        with self._connect() as connection:
            if not self._enabled(connection):
                if require_enabled:
                    raise AppError(
                        ErrorCode.WORKSPACE_CONFLICT,
                        message="Workspace memory was paused before the source lookup completed.",
                    )
                return
            self.workspace.get(self.workspace_id)
            if not self._claim_operation(connection, "capture", event_id):
                return
            topic = " ".join(sorted(terms))
            timestamp = datetime.now(UTC).isoformat()
            provenance = {**provenance, "topic_label": topic_label(topic_question)}
            for record_id, category, origin, content, parent, relation in (
                (event_id, "episode", "user_provided", question, None, None),
                (
                    f"{event_id}-concept",
                    "semantic",
                    "source_grounded",
                    answer,
                    event_id,
                    "discussed_in",
                ),
                (
                    f"{event_id}-excerpt",
                    "derived",
                    "generated",
                    answer[:300] + ("…" if len(answer) > 300 else ""),
                    f"{event_id}-concept",
                    "excerpt_of",
                ),
            ):
                self._insert(
                    connection,
                    record_id,
                    category,
                    origin,
                    content,
                    topic,
                    terms,
                    timestamp,
                    {**provenance, "parent_revision": 1} if parent else provenance,
                    parent,
                    relation,
                )

    @staticmethod
    def _insert(
        connection: sqlite3.Connection,
        record_id: str,
        category: Category,
        origin: str,
        text: str,
        topic: str,
        terms: tuple[str, ...],
        timestamp: str,
        provenance: dict[str, Any],
        parent_id: str | None,
        relation: str | None,
    ) -> None:
        connection.execute(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, '[]', ?, ?)",
            (
                record_id,
                category,
                origin,
                topic,
                json.dumps(terms),
                text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…",
                timestamp,
                json.dumps(provenance),
                parent_id,
                relation,
            ),
        )
        WorkspaceMemory._replace_terms(connection, record_id, terms, timestamp)

    @staticmethod
    def _replace_terms(
        connection: sqlite3.Connection,
        record_id: str,
        terms: tuple[str, ...],
        timestamp: str,
    ) -> None:
        connection.execute("DELETE FROM record_terms WHERE id = ?", (record_id,))
        connection.executemany(
            "INSERT INTO record_terms VALUES (?, ?, ?)",
            ((term, record_id, timestamp) for term in terms),
        )

    def add_note(self, parent_id: str, text: str, operation_id: str) -> None:
        """Keep a learner note linked to an existing discussion or concept."""
        self.workspace.get(self.workspace_id)
        with self._connect() as connection:
            identity = sha256(operation_id.encode()).hexdigest()
            if not self._claim_operation(connection, "note", identity):
                return
            if not self._enabled(connection):
                raise AppError(ErrorCode.WORKSPACE_CONFLICT)
            parent = self._get(connection, parent_id)
            if parent["category"] == "learning":
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Attach notes to a discussion, concept or study excerpt.",
                )
            self._insert(
                connection,
                uuid4().hex,
                "learning",
                "user_provided",
                text,
                parent["topic"],
                _terms(text),
                datetime.now(UTC).isoformat(),
                {"parent_revision": parent["revision"]},
                parent_id,
                "note_on",
            )

    def _resolve_aid(
        self,
        connection: sqlite3.Connection,
        aid: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        sources = {}
        rows = []
        for row in aid["coverage"]:
            row = dict(row)
            record_id = row["source_record_id"]
            if record_id and record_id not in sources:
                record = self._get(connection, record_id)
                if record["category"] not in {"episode", "semantic"}:
                    raise AppError(
                        ErrorCode.REQUEST_INVALID,
                        message="Select a discussion or concept as a reference.",
                    )
                sources[record_id] = {
                    "record_id": record_id,
                    "revision": record["revision"],
                    "provenance": json.loads(record["provenance"]),
                }
            if record_id:
                proof = sources[record_id]["provenance"].get("verified_definitions", [])
                for entry in proof:
                    if all(
                        row[key] == entry[key]
                        for key in ("original", "term", "definition")
                    ):
                        row["origin"] = "source_grounded"
                        row["citation"] = entry["citation"]
                        break
            rows.append(row)
        resolved = {**aid, "coverage": rows}
        if (
            len(sources) == 1
            and rows
            and all(row["origin"] == "source_grounded" for row in rows)
        ):
            provenance = next(iter(sources.values()))["provenance"]
            if aid["cue"] == provenance.get("verified_initials"):
                resolved["suggested_phrase"] = provenance.get("suggested_phrase")
        return resolved, sources

    def preview_study_aid(self, aid: dict[str, Any]) -> dict[str, Any]:
        self.workspace.get(self.workspace_id)
        if not any(row["source_record_id"] for row in aid["coverage"]):
            return aid
        with self._connect() as connection:
            return self._resolve_aid(connection, aid)[0]

    def save_study_aid(
        self,
        aid: dict[str, Any],
        operation_id: str,
        *,
        record_id: str | None = None,
        expected_revision: int | None = None,
    ) -> None:
        """Save or revise the cue, coverage, lineage and searchable text together."""
        self.workspace.get(self.workspace_id)
        with self._connect() as connection:
            identity = sha256(
                (f"{record_id}:{operation_id}" if record_id else operation_id).encode()
            ).hexdigest()
            kind = "study_aid_revision" if record_id else "study_aid"
            if not self._claim_operation(connection, kind, identity):
                return
            if not self._enabled(connection):
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    message="Enable workspace memory to save a study aid.",
                )
            if not aid["coverage"]:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Supply at least one known concept.",
                )
            aid, sources = self._resolve_aid(connection, aid)
            lines = [aid["title"], f"Cue: {aid['cue']}"]
            if aid.get("suggested_phrase"):
                lines.append(f"Suggested phrase: {aid['suggested_phrase']}")
            if aid["missing"]:
                lines.append("Missing definitions: " + ", ".join(aid["missing"]))
            for row in aid["coverage"]:
                lines.append(
                    f"{row['cue']} · {row['original']} · {row['term']} — {row['definition']}"
                )
            text = "\n".join(lines)
            if len(text) > MAX_TEXT:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Shorten the definitions before saving.",
                )
            provenance = {
                "study_aid": aid,
                "references": list(sources.values()),
                "topic_label": aid["title"],
            }
            topic = aid["title"].casefold()
            terms = _terms(text)
            timestamp = datetime.now(UTC).isoformat()
            if record_id is None:
                record_id = uuid4().hex
                self._insert(
                    connection,
                    record_id,
                    "derived",
                    "generated",
                    text,
                    topic,
                    terms,
                    timestamp,
                    provenance,
                    None,
                    None,
                )
            else:
                old = self._get(connection, record_id)
                old_provenance = json.loads(old["provenance"])
                if (
                    old["revision"] != expected_revision
                    or "study_aid" not in old_provenance
                ):
                    raise AppError(ErrorCode.WORKSPACE_CONFLICT)
                history = json.loads(old["history"])
                if len(history) >= MAX_REVISIONS - 1:
                    raise AppError(
                        ErrorCode.WORKSPACE_CONFLICT,
                        message="This item has reached its correction limit.",
                    )
                history.append(
                    {
                        "revision": old["revision"],
                        "text": old["text"],
                        "origin": old["origin"],
                        "corrected_at": timestamp,
                        "provenance": old_provenance,
                    }
                )
                connection.execute(
                    """
                    UPDATE records SET text = ?, topic = ?, terms = ?, provenance = ?,
                    revision = revision + 1, history = ?, origin = 'generated' WHERE id = ?
                """,
                    (
                        text,
                        topic,
                        json.dumps(terms),
                        json.dumps(provenance),
                        json.dumps(history),
                        record_id,
                    ),
                )
                self._replace_terms(connection, record_id, terms, old["created_at"])
                connection.execute("DELETE FROM study_aids WHERE id = ?", (record_id,))
            connection.execute(
                "INSERT INTO study_aids VALUES (?, ?)", (topic, record_id)
            )
            # Older revisions preserve dependencies as long as their text survives.
            connection.executemany(
                "INSERT OR IGNORE INTO study_inputs VALUES (?, ?)",
                ((parent, record_id) for parent in sources),
            )

    def training_review_records(self, query: str) -> tuple[bool, list[dict[str, Any]]]:
        """Read separate bounded pools so activity never displaces materials."""
        self.workspace.get(self.workspace_id)
        if not self.path.is_file():
            return False, []
        terms = topic_terms(query)
        with self._connect() as connection:
            enabled = self._enabled(connection)
            if query.strip() and not terms:
                return enabled, []
            pools = (
                "category = 'episode'",
                "category = 'semantic'",
                "category = 'learning' AND json_type(provenance, '$.training_outcome') IS NOT NULL",
                "category = 'derived' AND json_type(provenance, '$.training_card') IS NOT NULL",
                "category = 'derived' AND json_type(provenance, '$.study_aid') IS NOT NULL",
            )
            # Predicates come only from the fixed pool definitions. Terms remain
            # parameters, and membership is checked against the current index.
            filters = " ".join(
                "AND EXISTS (SELECT 1 FROM record_terms t WHERE t.id = records.id AND t.term = ?)"
                for _ in terms
            )
            records = []
            for pool in pools:
                rows = connection.execute(
                    f"SELECT id, category, origin, topic, text, revision, provenance, parent_id FROM records "
                    f"WHERE {pool} {filters} ORDER BY created_at DESC, id LIMIT ?",
                    (*terms, RECALL_LIMIT),
                )
                for row in rows:
                    record = dict(row)
                    record["provenance"] = json.loads(record["provenance"])
                    records.append(record)
            return enabled, records

    def training_card_saved(self, operation_id: str) -> bool:
        if not self.path.is_file():
            return False
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM processed_operations WHERE kind = 'training_card' AND identity = ?",
                    (sha256(operation_id.encode()).hexdigest(),),
                ).fetchone()
                is not None
            )

    def save_training_card(
        self,
        card: dict[str, Any],
        *,
        snapshot_id: str,
        workspace_revision: int,
        query_trace_id: str | None,
        operation_id: str,
    ) -> None:
        self.workspace.get(self.workspace_id)
        with self._connect() as connection:
            identity = sha256(operation_id.encode()).hexdigest()
            if not self._claim_operation(connection, "training_card", identity):
                return
            if not self._enabled(connection):
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    message="Enable workspace memory to save training materials.",
                )
            terms = topic_terms(card["topic"])
            topic = " ".join(sorted(terms))
            self._insert(
                connection,
                uuid4().hex,
                "derived",
                "generated",
                card["statement"],
                topic,
                terms,
                datetime.now(UTC).isoformat(),
                {
                    "training_card": card,
                    "topic_label": topic_label(card["topic"]),
                    "snapshot_id": snapshot_id,
                    "workspace_revision": workspace_revision,
                    "query_trace_id": query_trace_id,
                    "citations": [card["citation"]],
                },
                None,
                None,
            )

    def record_training_attempt(
        self,
        record_id: str,
        *,
        mode: str,
        answer: str,
        source_ids: list[str],
        operation_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            workspace = self.workspace.get(self.workspace_id)
            if not self._enabled(connection):
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    message="Enable memory to record practice.",
                )
            parent = self._get(connection, record_id)
            provenance = json.loads(parent["provenance"])
            card = provenance.get("training_card")
            if not card:
                raise AppError(ErrorCode.REQUEST_INVALID)
            if provenance["snapshot_id"] != workspace.current_snapshot_id:
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    message="Regenerate this card from the current publication.",
                )
            active = {
                (item.source_id, item.version)
                for item in workspace.sources
                if item.active
            }
            citation = card["citation"]
            if (
                citation["source_id"] not in source_ids
                or (citation["source_id"], citation["source_version"]) not in active
            ):
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Select the source linked to this card before practicing.",
                )
            attempt_id = "attempt_" + sha256(operation_id.encode()).hexdigest()
            if not self._claim_operation(connection, "training_attempt", attempt_id):
                previous = self._get(connection, attempt_id)
                if previous["parent_id"] != record_id:
                    raise AppError(ErrorCode.IDEMPOTENCY_CONFLICT)
                outcome = json.loads(previous["provenance"])["training_outcome"]
            else:
                if mode == "reveal":
                    outcome = "revealed"
                elif not answer.strip():
                    raise AppError(
                        ErrorCode.REQUEST_INVALID,
                        message="Enter an answer before checking.",
                    )
                elif answer.strip().casefold() != card["expected"].casefold():
                    outcome = "missed"
                else:
                    revealed = connection.execute(
                        """
                        SELECT 1 FROM records WHERE parent_id = ?
                        AND json_extract(provenance, '$.training_outcome') = 'revealed' LIMIT 1
                    """,
                        (record_id,),
                    ).fetchone()
                    outcome = "assisted" if revealed else "matched"
                self._insert(
                    connection,
                    attempt_id,
                    "learning",
                    "user_provided",
                    {
                        "revealed": "Reviewed the source answer",
                        "missed": "Practiced recall",
                        "assisted": "Matched after reviewing",
                        "matched": "Matched without revealing",
                    }[outcome],
                    parent["topic"],
                    tuple(json.loads(parent["terms"])),
                    datetime.now(UTC).isoformat(),
                    {
                        "training_outcome": outcome,
                        "snapshot_id": provenance["snapshot_id"],
                        "topic_label": provenance["topic_label"],
                        "parent_revision": parent["revision"],
                    },
                    record_id,
                    "practiced_with",
                )
            result = {"outcome": outcome}
            if outcome == "revealed":
                result["statement"] = card["statement"]
            return result

    def find_study_aids(self, title: str) -> list[dict[str, str]]:
        """Resolve a bounded exact title in this workspace."""
        self.workspace.get(self.workspace_id)
        if not self.path.is_file():
            return []
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT records.text FROM study_aids JOIN records USING (id) WHERE title_key = ? LIMIT 2",
                    (title.strip().casefold(),),
                )
            ]

    @staticmethod
    def _get(connection: sqlite3.Connection, record_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM records WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise AppError(ErrorCode.DOCUMENT_UNKNOWN)
        return row

    def change(self, record_id: str, revision: int, text: str | None) -> None:
        """Correct with compare-and-set or forget the record and dependents."""
        self.workspace.get(self.workspace_id)
        with self._connect() as connection:
            row = self._get(connection, record_id)
            if row["revision"] != revision:
                raise AppError(ErrorCode.WORKSPACE_CONFLICT)
            if text is None:
                connection.execute("DELETE FROM records WHERE id = ?", (record_id,))
                return
            provenance = json.loads(row["provenance"])
            if provenance.get("training_outcome"):
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Assessment outcomes can be forgotten, but cannot be edited.",
                )
            if provenance.get("training_card"):
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Regenerate the card from its source to correct it.",
                )
            if "study_aid" in provenance:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    message="Use the structured study aid editor to revise this item.",
                )
            # An excerpt reflects exactly one revision of its concept.
            connection.execute(
                "DELETE FROM records WHERE parent_id = ? AND relation = 'excerpt_of'",
                (record_id,),
            )
            history = json.loads(row["history"])
            if len(history) >= MAX_REVISIONS - 1:
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    message="This item has reached its correction limit.",
                )
            history.append(
                {
                    "revision": revision,
                    "text": row["text"],
                    "origin": row["origin"],
                    "corrected_at": datetime.now(UTC).isoformat(),
                }
            )
            terms = _terms(text)
            connection.execute(
                "UPDATE records SET text = ?, terms = ?, origin = 'user_provided', revision = ?, history = ? WHERE id = ?",
                (text, json.dumps(terms), revision + 1, json.dumps(history), record_id),
            )
            self._replace_terms(connection, record_id, terms, row["created_at"])

    @staticmethod
    def _extend_semantic_recall(
        query: str,
        embed: SemanticEmbed,
        candidates: list[dict[str, Any]],
        records: list[dict[str, Any]],
        topics: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Associate retrieved discussions without merging stored topic identities."""
        started = perf_counter()
        try:
            for record in candidates:
                for key in ("terms", "history", "provenance"):
                    record[key] = json.loads(record[key])
            descriptions = []
            for record in candidates:
                label = record["provenance"].get("topic_label", record["topic"])
                if record["origin"] == "user_provided" or len(topic_terms(label)) < 2:
                    label = record["text"][:700]
                descriptions.append(label)
            vectors = embed([query, *descriptions])
            if len(vectors) != len(candidates) + 1:
                return
            scored = sorted(
                (
                    (_cosine(vectors[0], vector), index)
                    for index, vector in enumerate(vectors[1:])
                ),
                key=lambda item: (-item[0], item[1]),
            )
            known_ids = {item["id"] for item in records}
            for score, index in scored:
                if not math.isfinite(score) or score < SEMANTIC_RECALL_MIN_COSINE or len(records) >= RECALL_LIMIT:
                    break
                record = candidates[index]
                if record["id"] in known_ids:
                    continue
                records.append(record)
            related = [record for record in records if record["category"] == "semantic"]
            if len({record["topic"] for record in related}) > 1:
                # A query-time related group is a view, not a stored merge or edit.
                topics.clear()
                topics[query] = [
                    {
                        "record_id": record["id"],
                        "text": record["text"][:300],
                        "revision": record["revision"],
                        "origin": record["origin"],
                    }
                    for record in related
                ]
        except Exception:
            logger.debug("Semantic memory recall unavailable; retaining lexical recall", exc_info=True)
        finally:
            logger.info("Memory association candidates=%s elapsed_ms=%.1f", len(candidates), (perf_counter() - started) * 1000)

    def recall(self, query: str, *, embed: SemanticEmbed | None = None) -> dict[str, Any]:
        """Recall a bounded set of recent or literal topic-matching records."""
        self.workspace.get(self.workspace_id)
        if not self.path.is_file():
            return {"enabled": False, "records": [], "summaries": []}
        terms = topic_terms(query)
        semantic_candidates = []
        with self._connect() as connection:
            enabled = self._enabled(connection)
            # Acronyms, single terms and identifiers keep exact recall semantics.
            if enabled and embed is not None and len(terms) >= 2 and not re.search(
                r"\b[A-Z]{2,}\b|[0-9]", query
            ):
                semantic_candidates = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM records WHERE category = 'semantic' "
                        "ORDER BY created_at DESC, id LIMIT ?",
                        (RECALL_LIMIT,),
                    )
                ]
            if query.strip() and not terms:
                rows = []
            elif terms:
                # Bound the per-term index scan independently of total history size.
                matches = set()
                for term in terms:
                    matches.update(
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM record_terms WHERE term = ? ORDER BY created_at DESC, id LIMIT ?",
                            (term, RECALL_LIMIT),
                        )
                    )
                if matches:
                    placeholders = ", ".join("?" for _ in matches)
                    rows = connection.execute(
                        f"SELECT * FROM records WHERE id IN ({placeholders}) ORDER BY created_at DESC, id",
                        tuple(matches),
                    )
                else:
                    rows = []
            else:
                rows = list(
                    connection.execute(
                        "SELECT * FROM records ORDER BY created_at DESC, id LIMIT ?",
                        (RECALL_LIMIT,),
                    )
                )
            records = []
            required_terms = set(terms)
            topics: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                record = dict(row)
                record["terms"] = json.loads(record["terms"])
                if not required_terms.issubset(record["terms"]):
                    continue
                for key in ("history", "provenance"):
                    record[key] = json.loads(record[key])
                records.append(record)
                if record["category"] == "semantic":
                    topics.setdefault(record["topic"], []).append(
                        {
                            "record_id": record["id"],
                            "text": record["text"][:300]
                            + ("…" if len(record["text"]) > 300 else ""),
                            "revision": record["revision"],
                            "origin": record["origin"],
                        }
                    )
                if len(records) >= RECALL_LIMIT:
                    break
        if semantic_candidates and embed is not None:
            self._extend_semantic_recall(query, embed, semantic_candidates, records, topics)
            # Discard stale selections if a learner corrected or forgot a record
            # while encoding, without holding a write lock around inference.
            with self._connect() as connection:
                current = {
                    row["id"]: row["revision"]
                    for row in connection.execute(
                        "SELECT id, revision FROM records WHERE id IN ("
                        + ", ".join("?" for _ in records) + ")",
                        [record["id"] for record in records],
                    )
                }
                enabled = self._enabled(connection)
            records = [
                record for record in records
                if current.get(record["id"]) == record["revision"] and enabled
            ]
            kept = {record["id"] for record in records}
            topics = {
                topic: [item for item in items if item["record_id"] in kept]
                for topic, items in topics.items()
            }
        return {
            "enabled": enabled,
            "records": records,
            "summaries": [
                {
                    "topic": topic,
                    "category": "derived",
                    "origin": "generated",
                    "items": items,
                    "label": query if topic == query else next(
                        record["provenance"].get("topic_label", topic)
                        for record in records
                        if record["id"] == items[0]["record_id"]
                    ),
                }
                for topic, items in topics.items()
                if len(items) > 1
            ],
        }
