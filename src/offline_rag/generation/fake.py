"""Test-only FakeGenerator — never an automatic production fallback."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from offline_rag.generation.contracts import FAKE_CONTRACT
from offline_rag.generation.protocol import (
    GeneratorProbeResult,
    GeneratorRequest,
    GeneratorResponse,
)


class FakeGeneratorError(RuntimeError):
    pass


class FakeGenerator:
    """Deterministic injectable generator for unit/CI tests."""

    contract = FAKE_CONTRACT

    def __init__(
        self,
        *,
        responses: Mapping[str, str] | None = None,
        default_response: str | None = None,
        response_fn: Callable[[GeneratorRequest], str] | None = None,
        probe_ok: bool = True,
        available_models: tuple[str, ...] = (),
        raise_on_generate: Exception | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default_response
        self._response_fn = response_fn
        self._probe_ok = probe_ok
        self._available_models = available_models
        self._raise_on_generate = raise_on_generate
        self.generate_calls = 0
        self.probe_calls = 0

    def generate(self, request: GeneratorRequest) -> GeneratorResponse:
        self.generate_calls += 1
        if self._raise_on_generate is not None:
            raise self._raise_on_generate
        if self._response_fn is not None:
            content = self._response_fn(request)
        else:
            query_key = ""
            for message in request.messages:
                if message.role == "user":
                    query_key = message.content
                    break
            content = self._responses.get(query_key, self._default)
            if content is None:
                raise FakeGeneratorError("no fake response configured for request")
        return GeneratorResponse(content=content, usage={}, raw={"fake": True})

    def probe(self) -> GeneratorProbeResult:
        self.probe_calls += 1
        if not self._probe_ok:
            return GeneratorProbeResult(ok=False, reason="fake probe failed")
        return GeneratorProbeResult(
            ok=True,
            reason="ok",
            available_models=self._available_models,
        )
