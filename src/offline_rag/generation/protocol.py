"""Generator protocol and request/response types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class GeneratorRequest:
    messages: tuple[ChatMessage, ...]
    model: str
    temperature: float
    max_output_tokens: int
    response_format: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratorResponse:
    content: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratorProbeResult:
    ok: bool
    reason: str
    available_models: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


class Generator(Protocol):
    def generate(self, request: GeneratorRequest) -> GeneratorResponse:
        """Return a single generator response (no retries)."""

    def probe(self) -> GeneratorProbeResult:
        """Non-generative readiness probe."""
