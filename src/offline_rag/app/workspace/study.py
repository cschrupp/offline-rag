"""Deterministic learner-facing recall and study aid composition."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.app.workspace.memory import MAX_TEXT, SemanticEmbed, WorkspaceMemory
from offline_rag.app.workspace.models import WorkspaceRecord
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings

_HISTORY = re.compile(
    r"(?:please )?(?:(?:summarize|recall|review|tell me) (?:what (?:i|we)(?: have|'ve)? "
    r"(?:learned|discussed|studied))|what (?:did|have) (?:i|we) (?:learn(?:ed)?|discuss(?:ed)?|study|studied))"
    r"(?: (?:about|on) (?P<topic>[\w ,'-]{1,240}))?[?.!]*",
    re.IGNORECASE,
)
_AID = re.compile(
    r"(?:recall|show me) (?:my |the )?(?:saved )?(?:study aid|mnemonic) (?P<title>[\w '-]{1,120})[?.!]*",
    re.IGNORECASE,
)


def is_learning_history_request(question: str) -> bool:
    """Recognize only explicit, standalone requests about learning history."""
    return bool(_HISTORY.fullmatch(question) or _AID.fullmatch(question))


class StudyConcept(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    term: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=240)


class MnemonicInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=48)
    concepts: list[StudyConcept] = Field(max_length=10)
    incomplete: bool = False
    source_record_id: str | None = Field(default=None, max_length=128)


class StudyAidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120, pattern=r"^[\w '-]+$")
    inputs: list[MnemonicInput] = Field(min_length=1, max_length=3)


def compose_study_aid(request: StudyAidRequest) -> dict[str, Any]:
    """Make a cue and retain one coverage row per supplied concept."""
    rows = []
    missing = []
    cues: dict[tuple[str, str], tuple[int, str]] = {}
    for group in request.inputs:
        if not group.concepts or group.incomplete:
            missing.append(group.name)
        for concept in group.concepts:
            key = (concept.term, concept.definition)
            initial = next(
                (char.upper() for char in concept.term if char.isalnum()), "•"
            )
            position, cue = cues.setdefault(key, (len(cues) + 1, initial))
            rows.append(
                {
                    "original": group.name,
                    "term": concept.term,
                    "definition": concept.definition,
                    "cue": f"{position}. {cue}",
                    "origin": "user_provided",
                    "source_record_id": group.source_record_id,
                }
            )
    cue = " · ".join(letter for _, letter in cues.values())
    return {
        "title": request.title,
        "inputs": [group.model_dump() for group in request.inputs],
        "cue": cue,
        "coverage": rows,
        "missing": missing,
        "complete": bool(rows) and not missing,
    }


def learning_history_response(
    settings: AppSettings, workspace_id: str, question: str, *, embed: SemanticEmbed | None = None
) -> dict[str, Any] | None:
    """Route explicit learning-history requests outside the grounded query."""
    history = _HISTORY.fullmatch(question)
    aid = _AID.fullmatch(question)
    if history is None and aid is None:
        return None
    record = WorkspaceStore(settings).get(workspace_id)
    memory = WorkspaceMemory(settings, workspace_id)
    if aid is not None:
        items = memory.find_study_aids(aid["title"])
        if len(items) == 1:
            answer = items[0]["text"]
        elif items:
            answer = "More than one saved study aid has that title. Open Knowledge to choose one."
        else:
            answer = "I couldn't find a saved study aid with that title in this workspace. Check its title in Knowledge."
    else:
        topics = memory.recall(history["topic"] or "", embed=embed)["records"]
        concepts = [item for item in topics if item["category"] == "semantic"]
        grouped: dict[str, list[str]] = {}
        for item in concepts[:12]:
            label = item["provenance"].get("topic_label", item["topic"])
            # Group by identity even if different discussions used different wording.
            key = item["topic"]
            group = grouped.setdefault(key, [label])
            snapshot = item["provenance"].get("snapshot_id")
            status = (
                "prior publication"
                if snapshot != record.current_snapshot_id
                else "saved discussion"
            )
            highlights = item["provenance"].get("concept_highlights", [])
            text = item["text"]
            if highlights and item["origin"] == "source_grounded":
                text = " / ".join(highlights)
            origin = (
                "learner correction" if item["origin"] == "user_provided" else status
            )
            excerpt = f"• {text[:360]}{'…' if len(text) > 360 else ''} ({origin})"
            if excerpt not in group:
                group.append(excerpt)
        answer = "\n\n".join("\n".join(group) for group in grouped.values())[:MAX_TEXT]
        if not answer:
            answer = "I couldn't find matching discussions in this workspace's Knowledge panel."
    return memory_response(record, question, answer)


def memory_response(
    record: WorkspaceRecord, question: str, answer: str
) -> dict[str, Any]:
    """Produce an ephemeral learning-history response without factual citations."""
    return {
        "workspace_id": record.workspace_id,
        "workspace_revision": int(record.revision),
        "snapshot_id": record.current_snapshot_id or "",
        "product_mode_id": "knowledge_recall_v1",
        "conversation_trace_id": f"memory_{uuid4().hex}",
        "query_trace_id": None,
        "status": "answered",
        "abstention_reason": None,
        "question": question,
        "retrieval_question": None,
        "context_used": False,
        "answer": answer,
        "answer_blocks": [],
        "citations": [],
        "answer_origin": "conversation",
        "memory_recall": True,
    }
