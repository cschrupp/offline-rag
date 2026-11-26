"""Local workspace learning records and bounded topic recall."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings

Category = Literal["episode", "semantic", "learning", "derived"]
MAX_TEXT = 6000
MAX_REVISIONS = 20
RECALL_LIMIT = 24
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
            if "study_aid" in json.loads(row["provenance"]):
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

    def recall(self, query: str) -> dict[str, Any]:
        """Recall a bounded set of recent or literal topic-matching records."""
        self.workspace.get(self.workspace_id)
        if not self.path.is_file():
            return {"enabled": False, "records": [], "summaries": []}
        terms = topic_terms(query)
        with self._connect() as connection:
            enabled = self._enabled(connection)
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
        return {
            "enabled": enabled,
            "records": records,
            "summaries": [
                {
                    "topic": topic,
                    "category": "derived",
                    "origin": "generated",
                    "items": items,
                    "label": next(
                        record["provenance"].get("topic_label", topic)
                        for record in records
                        if record["id"] == items[0]["record_id"]
                    ),
                }
                for topic, items in topics.items()
                if len(items) > 1
            ],
        }
