"""relevance-judge-context-v1 envelope rendering."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.core.document_metadata import (
    DocumentMetadataError,
    render_section_path_v1,
    resolve_document_title_v1,
)
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.contracts import JUDGE_CONTEXT_CONTRACT


class JudgeContextError(RuntimeError):
    """Required judge-visible context could not be constructed."""


@dataclass(frozen=True, slots=True)
class RelevanceJudgeContext:
    query: str
    document_title: str
    section_path: tuple[str, ...]
    text: str

    def render_user_message(self) -> str:
        lines = [
            "QUERY:",
            self.query,
            "",
            "DOCUMENT:",
            self.document_title,
        ]
        section = render_section_path_v1(self.section_path)
        if section is not None:
            lines.extend(["", "SECTION:", section])
        lines.extend(["", "CANDIDATE:", self.text])
        return "\n".join(lines)


def build_relevance_judge_context(
    *,
    query: str,
    chunk: Chunk,
    source_name: str | None,
) -> RelevanceJudgeContext:
    if chunk.kind != ChunkKind.CHILD:
        raise JudgeContextError(
            f"candidate {chunk.chunk_id} is not a child chunk"
        )
    if not str(query).strip():
        raise JudgeContextError("query is blank")
    if source_name is None or not str(source_name).strip():
        raise JudgeContextError(
            f"authoritative source_name missing for document_id={chunk.document_id}"
        )
    try:
        title = resolve_document_title_v1(str(source_name))
    except DocumentMetadataError as exc:
        raise JudgeContextError(str(exc)) from exc
    return RelevanceJudgeContext(
        query=str(query).strip(),
        document_title=title,
        section_path=tuple(chunk.section_path),
        text=chunk.text,
    )


def judge_context_contract_id() -> str:
    return JUDGE_CONTEXT_CONTRACT
