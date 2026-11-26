"""Workspace memory activities and a deterministic, source-linked review exercise."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.workspace.memory import WorkspaceMemory
from offline_rag.app.workspace.models import WorkspaceRecord


class TrainingCardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(min_length=1, max_length=160)
    source_ids: list[str] = Field(min_length=1, max_length=64)


class TrainingAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_ids: list[str] = Field(min_length=1, max_length=64)
    mode: Literal["reveal", "check"]
    answer: str = Field(default="", max_length=160)


def card_from_answer(
    topic: str, blocks: list[dict[str, Any]], citations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build an exercise from one exact statement in its cited evidence."""
    by_ref = {row["citation_ref"]: row for row in citations}
    for block in blocks[:4]:
        statement = " ".join(block["text"].split())
        if not 30 <= len(statement) <= 240:
            continue
        words = list(re.finditer(r"\b[^\W_]{4,}\b", statement))
        if not words:
            continue
        for ref in block["citation_refs"]:
            citation = by_ref.get(ref)
            if not citation:
                continue
            excerpt = " ".join(citation.get("excerpt", "").split())
            if statement not in excerpt:
                continue
            if citation.get("excerpt_clipped") and excerpt.endswith(statement):
                continue
            word = words[-1]
            # Choose one unambiguous blank. A repeated answer elsewhere on the
            # card would make the exercise measure copying rather than recall.
            if (
                len(
                    re.findall(
                        rf"\b{re.escape(word.group())}\b", statement, re.IGNORECASE
                    )
                )
                != 1
            ):
                continue
            return {
                "topic": topic,
                "flashcard_question": f"What statement did the selected source make about {topic}?",
                "statement": statement,
                "exercise": statement[: word.start()]
                + "____"
                + statement[word.end() :],
                "expected": word.group(),
                "citation": {
                    key: citation.get(key)
                    for key in (
                        "source_id",
                        "source_version",
                        "source_display_name",
                        "document_id",
                        "source_chunk_id",
                        "evidence_unit_id",
                    )
                },
            }
    raise AppError(
        ErrorCode.REQUEST_INVALID,
        message="No exact statement was verified in the selected evidence. Try a narrower topic or choose another source.",
    )


def training_view(
    memory: WorkspaceMemory,
    workspace: WorkspaceRecord,
    topic: str,
) -> dict[str, Any]:
    """Project bounded history without returning unrevealed card answers."""
    enabled, records = memory.training_review_records(topic)
    history: dict[str, dict[str, Any]] = {}
    topics: dict[str, dict[str, Any]] = {}
    cards = []
    aids = []
    assessed_cards: set[tuple[str, str, str]] = set()
    for item in records:
        provenance = item["provenance"]
        label = provenance.get("topic_label", item["topic"])
        progress = topics.setdefault(
            item["topic"],
            {
                "topic": label,
                "exposure": 0,
                "practice": 0,
                "current_matches": 0,
                "historical_matches": 0,
                "needs_revalidation": 0,
            },
        )
        card = provenance.get("training_card")
        if card:
            historical = provenance["snapshot_id"] != workspace.current_snapshot_id
            progress["needs_revalidation"] += int(historical)
            cards.append(
                {
                    "id": item["id"],
                    "topic": card["topic"],
                    "flashcard_question": card["flashcard_question"],
                    "exercise": card["exercise"],
                    "citation": card["citation"],
                    "snapshot_id": provenance["snapshot_id"],
                    "requires_revalidation": historical,
                }
            )
        elif "training_outcome" in provenance:
            progress["practice"] += 1
            if provenance["training_outcome"] == "matched":
                key = (
                    "current_matches"
                    if provenance["snapshot_id"] == workspace.current_snapshot_id
                    else "historical_matches"
                )
                identity = (item["topic"], key, item["parent_id"])
                if identity not in assessed_cards:
                    progress[key] += 1
                    assessed_cards.add(identity)
        elif item["category"] == "episode":
            if provenance.get("verified_definitions"):
                continue
            progress["exposure"] += 1
        elif item["category"] == "semantic":
            group = history.setdefault(
                item["topic"], {"topic": item["topic"], "label": label, "items": []}
            )
            group["items"].append(
                {
                    "record_id": item["id"],
                    "text": item["text"][:300],
                    "historical": provenance.get("snapshot_id")
                    != workspace.current_snapshot_id,
                    "origin": item["origin"],
                }
            )
        elif aid := provenance.get("study_aid"):
            snapshots = {
                ref["provenance"].get("snapshot_id")
                for ref in provenance.get("references", [])
            } - {None}
            aids.append(
                {
                    "id": item["id"],
                    "title": aid["title"],
                    "text": item["text"],
                    "origin": item["origin"],
                    "revision": item["revision"],
                    "references": provenance.get("references", []),
                    "requires_revalidation": any(
                        snapshot != workspace.current_snapshot_id
                        for snapshot in snapshots
                    ),
                }
            )
    for progress in topics.values():
        if progress["needs_revalidation"] or progress["historical_matches"]:
            recommendation = "Regenerate practice from the current sources."
        elif progress["current_matches"]:
            recommendation = "Try another exercise on this topic."
        elif progress["practice"]:
            recommendation = "Practice retrieving the answer before revealing it."
        elif progress["exposure"]:
            recommendation = "Create a card and try a recall exercise."
        else:
            recommendation = "Review this topic in Knowledge."
        progress["recommendation"] = recommendation
    return {
        "enabled": enabled,
        "cards": cards,
        "aids": aids,
        "history": list(history.values()),
        "topics": list(topics.values()),
    }
