"""Proposal context rendering (proposal-context-seed-provenance-v1)."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.core.document_metadata import (
    DocumentMetadataError,
    render_section_path_v1,
    resolve_document_title_v1,
)
from offline_rag.gold_authoring.contracts import CONTEXT_CONTRACT
from offline_rag.gold_authoring.sampling import EligibleChild


class ProposalContextError(RuntimeError):
    """Required proposal context could not be constructed."""


@dataclass(frozen=True, slots=True)
class ProposalSourceContext:
    chunk_id: str
    document_id: str
    document_title: str
    section_path: tuple[str, ...]
    text: str

    def render_user_message(self) -> str:
        lines = [f"DOCUMENT: {self.document_title}"]
        section = render_section_path_v1(self.section_path)
        if section is not None:
            lines.append(f"SECTION: {section}")
        lines.append("")
        lines.append(self.text)
        return "\n".join(lines)


def build_proposal_source_context(
    seed: EligibleChild,
    *,
    source_name: str | None,
) -> ProposalSourceContext:
    if source_name is None or not str(source_name).strip():
        raise ProposalContextError(
            f"authoritative source_name missing for document_id={seed.document_id}"
        )
    try:
        title = resolve_document_title_v1(str(source_name))
    except DocumentMetadataError as exc:
        raise ProposalContextError(str(exc)) from exc
    return ProposalSourceContext(
        chunk_id=seed.chunk_id,
        document_id=seed.document_id,
        document_title=title,
        section_path=seed.section_path,
        text=seed.text,
    )


def context_contract_id() -> str:
    return CONTEXT_CONTRACT
