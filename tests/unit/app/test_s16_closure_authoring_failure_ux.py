"""S16 closure — authoring-server failure UX (R1–R4 / Q1–Q6)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.gold_lab.bootstrap import (
    classify_zero_success_proposal,
    map_propose_pre_run_error,
)
from offline_rag.app.workspace.models import ManagedOperationSafeError
from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.gold_authoring.adapter import (
    AuthoringAdapterError,
    OpenAICompatibleAuthoringAdapter,
)
from offline_rag.gold_authoring.chunk_access import ChunkAccessError
from offline_rag.gold_authoring.models import (
    ProposalAttempt,
    ProposalAttemptStatus,
    ProposalFailureReason,
    SourceSeed,
)
from offline_rag.gold_authoring.propose import (
    ProposePreRunError,
    ProposePreRunReason,
    UnknownAdapterFailureError,
    _map_adapter_failure,
    run_gold_propose,
)


def _ready_settings(**overrides: Any) -> AppSettings:
    auth = {
        "enabled": True,
        "model": "test-model",
        "approved_models": ["test-model"],
        "approved_endpoints": ["http://127.0.0.1:11434/v1"],
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "author-secret",
        "network_policy": "localhost_only",
    }
    auth.update(overrides)
    return AppSettings(authoring=AuthoringSettings(**auth))


def _chunk(chunk_id: str = "chunk_01") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc_a",
        kind=ChunkKind.CHILD,
        text="Naturalistic Decision Making is useful for operators.",
        order=0,
        token_count=8,
        content_type="text",
        content_hash="hash",
        source_block_ids=["b1"],
        section_path=["SECTION"],
    )


def _attempt(reason: ProposalFailureReason) -> ProposalAttempt:
    return ProposalAttempt(
        source_seed=SourceSeed(chunk_id="c1", document_id="d1"),
        status=ProposalAttemptStatus.FAILED_TRANSPORT,
        failure_reason=reason,
    )


@pytest.mark.parametrize(
    ("reasons", "code", "safe"),
    [
        (
            [ProposalFailureReason.AUTHENTICATION_ERROR, ProposalFailureReason.TIMEOUT],
            ErrorCode.GOLD_CONFLICT,
            "authoring_authentication_failed",
        ),
        (
            [ProposalFailureReason.TIMEOUT, ProposalFailureReason.TRANSPORT_ERROR],
            ErrorCode.GOLD_CONFLICT,
            "authoring_request_timeout",
        ),
        (
            [ProposalFailureReason.TRANSPORT_ERROR, ProposalFailureReason.HTTP_ERROR],
            ErrorCode.GOLD_CONFLICT,
            "authoring_endpoint_unreachable",
        ),
        (
            [ProposalFailureReason.HTTP_ERROR, ProposalFailureReason.SCHEMA_INVALID],
            ErrorCode.GOLD_CONFLICT,
            "authoring_http_error",
        ),
        (
            [
                ProposalFailureReason.REDIRECT_NOT_ALLOWED,
                ProposalFailureReason.SCHEMA_INVALID,
            ],
            ErrorCode.GOLD_CONFLICT,
            "authoring_http_error",
        ),
        (
            [
                ProposalFailureReason.HTTP_ERROR,
                ProposalFailureReason.PROPOSAL_CONTEXT_UNAVAILABLE,
            ],
            ErrorCode.GOLD_CONFLICT,
            "authoring_http_error",
        ),
        (
            [
                ProposalFailureReason.PROPOSAL_CONTEXT_UNAVAILABLE,
                ProposalFailureReason.DEICTIC_QUERY,
            ],
            ErrorCode.INTERNAL_ERROR,
            "bootstrap_internal_failure",
        ),
        (
            [
                ProposalFailureReason.PROPOSAL_CONTEXT_UNAVAILABLE,
                ProposalFailureReason.INVALID_JSON,
            ],
            ErrorCode.INTERNAL_ERROR,
            "bootstrap_internal_failure",
        ),
        (
            [ProposalFailureReason.PROPOSAL_CONTEXT_UNAVAILABLE],
            ErrorCode.INTERNAL_ERROR,
            "bootstrap_internal_failure",
        ),
        (
            [ProposalFailureReason.SCHEMA_INVALID],
            ErrorCode.GOLD_CONFLICT,
            "zero_usable_proposals",
        ),
        (
            [ProposalFailureReason.EMPTY_RESPONSE, ProposalFailureReason.INVALID_JSON],
            ErrorCode.GOLD_CONFLICT,
            "zero_usable_proposals",
        ),
    ],
)
def test_classify_zero_success_priority(
    reasons: list[ProposalFailureReason],
    code: ErrorCode,
    safe: str,
) -> None:
    counts = Counter(r.value for r in reasons)
    attempts = [_attempt(r) for r in reasons]
    got_code, got_reason = classify_zero_success_proposal(counts, attempts)
    assert got_code is code
    assert got_reason == safe


def test_classify_fail_closed_empty_and_unknown() -> None:
    assert classify_zero_success_proposal(None, None) == (
        ErrorCode.INTERNAL_ERROR,
        "bootstrap_internal_failure",
    )
    assert classify_zero_success_proposal(Counter(), []) == (
        ErrorCode.INTERNAL_ERROR,
        "bootstrap_internal_failure",
    )
    assert classify_zero_success_proposal(
        Counter({"not_a_real_reason": 1}),
        None,
    ) == (ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure")


def test_map_propose_pre_run_structural() -> None:
    assert map_propose_pre_run_error(
        ProposePreRunError("x", reason=ProposePreRunReason.AUTHORING_NOT_READY)
    ) == (ErrorCode.GOLD_CONFLICT, "authoring_not_ready")
    assert map_propose_pre_run_error(
        ProposePreRunError(
            "x", reason=ProposePreRunReason.AUTHORING_ENDPOINT_UNAUTHORIZED
        )
    ) == (ErrorCode.GOLD_CONFLICT, "authoring_endpoint_unauthorized")
    assert map_propose_pre_run_error(
        ProposePreRunError(
            "x",
            reason=ProposePreRunReason.PROPOSAL_COUNT_EXCEEDS_ELIGIBLE_POPULATION,
        )
    ) == (ErrorCode.GOLD_CONFLICT, "proposal_count_exceeds_eligible_population")
    for reason in (
        ProposePreRunReason.NO_ELIGIBLE_POPULATION,
        ProposePreRunReason.PROPOSAL_COUNT_INVALID,
        ProposePreRunReason.OUTPUT_EXISTS,
        ProposePreRunReason.SOURCE_SNAPSHOT_UNAVAILABLE,
    ):
        assert map_propose_pre_run_error(
            ProposePreRunError("x", reason=reason)
        ) == (ErrorCode.INTERNAL_ERROR, "bootstrap_internal_failure")


def test_map_propose_pre_run_never_uses_message_text() -> None:
    exc = ProposePreRunError(
        "requested count 99 exceeds eligible population 1",
        reason=ProposePreRunReason.OUTPUT_EXISTS,
    )
    # Message mentions "exceeds eligible" but typed reason wins.
    assert map_propose_pre_run_error(exc) == (
        ErrorCode.INTERNAL_ERROR,
        "bootstrap_internal_failure",
    )


def test_adapter_http_status_provenance() -> None:
    settings = _ready_settings()

    def _post_status(status: int, *, is_redirect: bool = False) -> MagicMock:
        client = MagicMock()
        response = MagicMock()
        response.is_redirect = is_redirect
        response.status_code = status
        response.json.return_value = {}
        client.post.return_value = response
        return client

    for status in (401, 403):
        adapter = OpenAICompatibleAuthoringAdapter(
            settings, client=_post_status(status)
        )
        with pytest.raises(AuthoringAdapterError) as err:
            adapter.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
        assert err.value.failure_reason == "authentication_error"

    adapter = OpenAICompatibleAuthoringAdapter(settings, client=_post_status(500))
    with pytest.raises(AuthoringAdapterError) as err:
        adapter.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
    assert err.value.failure_reason == "http_error"

    adapter = OpenAICompatibleAuthoringAdapter(
        settings, client=_post_status(302, is_redirect=True)
    )
    with pytest.raises(AuthoringAdapterError) as err:
        adapter.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
    assert err.value.failure_reason == "redirect_not_allowed"


def test_adapter_timeout_and_transport() -> None:
    settings = _ready_settings()
    client = MagicMock()
    client.post.side_effect = httpx.TimeoutException("timed out")
    adapter = OpenAICompatibleAuthoringAdapter(settings, client=client)
    with pytest.raises(AuthoringAdapterError) as err:
        adapter.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
    assert err.value.failure_reason == "timeout"

    client2 = MagicMock()
    client2.post.side_effect = httpx.ConnectError("connection refused")
    adapter2 = OpenAICompatibleAuthoringAdapter(settings, client=client2)
    with pytest.raises(AuthoringAdapterError) as err2:
        adapter2.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
    assert err2.value.failure_reason == "transport_error"


def test_adapter_local_failures_are_not_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.gold_authoring.privacy import (
        AuthoringAuthReason,
        AuthoringPrivacyError,
    )
    from offline_rag.gold_authoring.readiness import AuthoringReadiness

    not_ready = AppSettings(authoring=AuthoringSettings(enabled=False))
    adapter = OpenAICompatibleAuthoringAdapter(not_ready, client=MagicMock())
    with pytest.raises(AuthoringAdapterError) as err:
        adapter.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
    assert err.value.failure_reason == "authoring_not_ready"

    # Readiness already folds allowlist failures into not-ready; force the
    # post-ready privacy path so adapter provenance is proven directly.
    monkeypatch.setattr(
        "offline_rag.gold_authoring.adapter.evaluate_authoring_readiness",
        lambda settings: AuthoringReadiness(ready=True),
    )
    monkeypatch.setattr(
        "offline_rag.gold_authoring.adapter.authorize_authoring_endpoint",
        lambda settings: (_ for _ in ()).throw(
            AuthoringPrivacyError(
                "configured authoring endpoint is not approved",
                reason=AuthoringAuthReason.ENDPOINT_NOT_APPROVED,
            )
        ),
    )
    adapter2 = OpenAICompatibleAuthoringAdapter(_ready_settings(), client=MagicMock())
    with pytest.raises(AuthoringAdapterError) as err2:
        adapter2.propose(system_prompt="s", user_content="DOCUMENT: X\n\nbody")
    assert err2.value.failure_reason == "authoring_endpoint_unauthorized"
    assert err2.value.failure_reason != "authentication_error"


def test_map_adapter_failure_unknown_fail_closed() -> None:
    with pytest.raises(UnknownAdapterFailureError):
        _map_adapter_failure("totally_unknown_adapter_reason")
    status, reason = _map_adapter_failure("transport_error")
    assert reason is ProposalFailureReason.TRANSPORT_ERROR
    assert status is ProposalAttemptStatus.FAILED_TRANSPORT


def test_typed_prerun_reasons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chunks = [_chunk("chunk_01"), _chunk("chunk_02")]

    def _install(chunks_arg: list[Chunk]) -> None:
        snap = CorpusChunkSnapshot(
            corpus_name="demo",
            corpus_id="corpus_demo",
            chunk_set_id="chunkset_demo",
            chunks=chunks_arg,
            source_name_by_document_id={"doc_a": "Doc A"},
        )

        def _load(settings: AppSettings, *, corpus_name: str) -> CorpusChunkSnapshot:
            _ = settings, corpus_name
            return snap

        monkeypatch.setattr(
            "offline_rag.gold_authoring.propose.load_current_corpus_chunk_snapshot",
            _load,
        )

    _install(chunks)

    with pytest.raises(ProposePreRunError) as not_ready:
        run_gold_propose(
            AppSettings(authoring=AuthoringSettings(enabled=False)),
            corpus_name="demo",
            count=1,
            seed=0,
        )
    assert not_ready.value.reason is ProposePreRunReason.AUTHORING_NOT_READY

    from offline_rag.gold_authoring.privacy import (
        AuthoringAuthReason,
        AuthoringPrivacyError,
    )
    from offline_rag.gold_authoring.propose import run_gold_propose_on_snapshot

    snap = CorpusChunkSnapshot(
        corpus_name="demo",
        corpus_id="corpus_demo",
        chunk_set_id="chunkset_demo",
        chunks=chunks,
        source_name_by_document_id={"doc_a": "Doc A"},
    )
    monkeypatch.setattr(
        "offline_rag.gold_authoring.propose.authorize_authoring_endpoint",
        lambda settings: (_ for _ in ()).throw(
            AuthoringPrivacyError(
                "configured authoring endpoint is not approved",
                reason=AuthoringAuthReason.ENDPOINT_NOT_APPROVED,
            )
        ),
    )
    with pytest.raises(ProposePreRunError) as unauthorized:
        run_gold_propose_on_snapshot(
            _ready_settings(),
            snapshot=snap,
            authoring_run_id="authorrun_test",
            count=1,
            seed=0,
            output=tmp_path / "out.json",
            force=True,
            skip_readiness=True,
        )
    assert (
        unauthorized.value.reason is ProposePreRunReason.AUTHORING_ENDPOINT_UNAUTHORIZED
    )
    monkeypatch.undo()

    _install([])
    with pytest.raises(ProposePreRunError) as empty:
        run_gold_propose(_ready_settings(), corpus_name="demo", count=1, seed=0)
    assert empty.value.reason is ProposePreRunReason.NO_ELIGIBLE_POPULATION

    _install(chunks)
    with pytest.raises(ProposePreRunError) as invalid_count:
        run_gold_propose(_ready_settings(), corpus_name="demo", count=0, seed=0)
    assert invalid_count.value.reason is ProposePreRunReason.PROPOSAL_COUNT_INVALID

    with pytest.raises(ProposePreRunError) as exceeds:
        run_gold_propose(_ready_settings(), corpus_name="demo", count=99, seed=0)
    assert (
        exceeds.value.reason
        is ProposePreRunReason.PROPOSAL_COUNT_EXCEEDS_ELIGIBLE_POPULATION
    )

    out = tmp_path / "exists.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(ProposePreRunError) as exists:
        run_gold_propose(
            _ready_settings(),
            corpus_name="demo",
            count=1,
            seed=0,
            output=out,
            force=False,
            adapter=MagicMock(),  # type: ignore[arg-type]
        )
    assert exists.value.reason is ProposePreRunReason.OUTPUT_EXISTS

    def _boom(settings: AppSettings, *, corpus_name: str) -> Any:
        raise ChunkAccessError("snapshot gone")

    monkeypatch.setattr(
        "offline_rag.gold_authoring.propose.load_current_corpus_chunk_snapshot",
        _boom,
    )
    with pytest.raises(ProposePreRunError) as snap:
        run_gold_propose(_ready_settings(), corpus_name="demo", count=1, seed=0)
    assert snap.value.reason is ProposePreRunReason.SOURCE_SNAPSHOT_UNAVAILABLE


def test_safe_error_details_non_leakage() -> None:
    details = SafeErrorDetails(reason="authoring_endpoint_unreachable")
    envelope = ManagedOperationSafeError.from_app_error(
        AppError(ErrorCode.GOLD_CONFLICT, details=details)
    )
    assert envelope.details == {"reason": "authoring_endpoint_unreachable"}
    assert "failure_reason_counts" not in (envelope.details or {})
    assert "http://127.0.0.1" not in str(envelope.model_dump())
    assert "author-secret" not in str(envelope.model_dump())


def test_transport_regression_not_zero_usable() -> None:
    code, reason = classify_zero_success_proposal(
        Counter({ProposalFailureReason.TRANSPORT_ERROR.value: 3}),
        [_attempt(ProposalFailureReason.TRANSPORT_ERROR)] * 3,
    )
    assert code is ErrorCode.GOLD_CONFLICT
    assert reason == "authoring_endpoint_unreachable"
    assert reason != "zero_usable_proposals"
