"""First-use publication and retry behavior for the shared reranker."""

import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from offline_rag.rerank import cross_encoder


@pytest.fixture
def loader(monkeypatch, tmp_path):
    monkeypatch.setattr(cross_encoder, "require_reranker_artifacts", Mock())
    model = Mock()
    model.parameters.return_value = []
    model.buffers.return_value = []
    load_model = Mock(return_value=model)
    load_tokenizer = Mock(return_value=object())
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=load_tokenizer),
            AutoModelForSequenceClassification=SimpleNamespace(
                from_pretrained=load_model
            ),
        ),
    )
    reranker = cross_encoder.CrossEncoderReranker(
        model_path=tmp_path,
        model_id="test",
        model_revision="test",
        adapter_contract="test",
        device="cpu",
    )
    return reranker, load_tokenizer, load_model, model


def test_overlapping_first_use_loads_once(loader):
    reranker, tokenizer, load_model, model = loader
    entered = Event()
    release = Event()
    second_attempt = Event()

    class ObservedLock:
        def __init__(self):
            self.lock = Lock()

        def __enter__(self):
            if self.lock.locked():
                second_attempt.set()
            self.lock.acquire()

        def __exit__(self, *_):
            self.lock.release()

    reranker._load_lock = ObservedLock()

    def initialize(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return model

    load_model.side_effect = initialize
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reranker._load)
        try:
            assert entered.wait(5)
            second = pool.submit(reranker._load)
            assert second_attempt.wait(5)
            assert reranker._loaded is None
        finally:
            release.set()
        assert first.result(timeout=5) is second.result(timeout=5)
    load_model.assert_called_once()
    tokenizer.assert_called_once()
    model.to.assert_called_once_with("cpu")
    reranker._load_lock = None
    assert reranker._load() is first.result()


def test_failed_transfer_leaves_no_state_and_retries(loader):
    reranker, load_tokenizer, load_model, model = loader
    model.to.side_effect = [RuntimeError("transfer failed"), None]
    with pytest.raises(RuntimeError, match="transfer failed"):
        reranker._load()
    assert reranker._loaded is None
    assert reranker._load()[1] is model
    assert load_model.call_count == load_tokenizer.call_count == 2


@pytest.mark.parametrize("member", ["parameters", "buffers"])
@pytest.mark.parametrize("after_transfer", [False, True])
def test_meta_state_is_rejected(loader, member, after_transfer):
    reranker, _, _, model = loader
    torch = pytest.importorskip("torch")
    meta = torch.empty(1, device="meta")
    if after_transfer:
        getattr(model, member).side_effect = [[], [meta]]
    else:
        getattr(model, member).return_value = [meta]

    with pytest.raises(
        cross_encoder.CrossEncoderRerankerError, match="unmaterialized meta"
    ):
        reranker._load()
    assert reranker._loaded is None
    assert model.to.called is after_transfer
