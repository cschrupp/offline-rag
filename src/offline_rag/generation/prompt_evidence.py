"""Generation-local immutable rendering input for prompt-grounded-provenance-v2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptEvidence:
    """Slice 8 prompt-adaptation DTO (not a Slice 7 EvidenceUnit replacement)."""

    evidence_unit_id: str
    document_title: str
    section_path: tuple[str, ...]
    text: str

    def __post_init__(self) -> None:
        if not self.evidence_unit_id or not str(self.evidence_unit_id).strip():
            raise ValueError("PromptEvidence.evidence_unit_id must be non-empty")
        if not self.document_title or not str(self.document_title).strip():
            raise ValueError("PromptEvidence.document_title must be non-empty")
        if not isinstance(self.text, str) or self.text == "":
            raise ValueError("PromptEvidence.text must be a non-empty string")
        if not isinstance(self.section_path, tuple):
            raise ValueError("PromptEvidence.section_path must be a tuple")
