"""P1 ONNX adapter unit tests (mocked; no multi-GB artifacts)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

# Path used by test_no_production_onnx_graph_import
import pytest
import torch

from offline_rag.dense.embedding_artifacts import (
    QUALIFICATION_SCHEMA,
    QualifiedEmbeddingRepresentationSpec,
    RepresentationInspection,
    RepresentationReadiness,
    RepresentationReasonCode,
)
from offline_rag.dense.onnx_embedder import (
    FROZEN_ONNX_PROVIDER,
    FROZEN_ORT_INTER_OP_THREADS,
    FROZEN_ORT_INTRA_OP_THREADS,
    OnnxEmbedderError,
    SentenceTransformersOnnxEmbedder,
    apply_seneca_onnx_position_ids_compat,
    build_qwen3_direct_forward_position_ids,
)


def _spec() -> QualifiedEmbeddingRepresentationSpec:
    return QualifiedEmbeddingRepresentationSpec(
        qualification_schema=QUALIFICATION_SCHEMA,
        representation_id="onnx_fp32_v1",
        model_id="Qwen/Qwen3-Embedding-0.6B",
        model_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        expected_dimension=1024,
        runtime_family="sentence_transformers_onnx",
        source_kind="test",
        source_repo_id="Qwen/Qwen3-Embedding-0.6B",
        source_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        required_files=("onnx/model.onnx",),
        expected_file_digests={"onnx/model.onnx": "0" * 64},
        runtime_contract={
            "provider": "CPUExecutionProvider",
            "graph_file_name": "onnx/model.onnx",
            "required_onnx_inputs": [
                "input_ids",
                "attention_mask",
                "position_ids",
            ],
        },
        qualification_evidence={},
    )


def _rep(tmp_path: Path) -> RepresentationInspection:
    return RepresentationInspection(
        representation_id="onnx_fp32_v1",
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=tmp_path,
        instance_path=tmp_path,
        graph_file_name="onnx/model.onnx",
        qualification_spec=_spec(),
    )


def test_position_ids_injected_when_absent() -> None:
    input_ids = torch.tensor([[1, 2, 3]], dtype=torch.long)
    # Non-all-ones mask so cumsum-1 differs from zero-based arange.
    attention_mask = torch.tensor([[1, 1, 0]], dtype=torch.long)
    features = {"input_ids": input_ids, "attention_mask": attention_mask}
    out = apply_seneca_onnx_position_ids_compat(
        features, required_onnx_inputs={"input_ids", "attention_mask", "position_ids"}
    )
    assert "position_ids" in out
    expected = build_qwen3_direct_forward_position_ids(input_ids)
    assert torch.equal(out["position_ids"], expected)
    cumsum_positions = attention_mask.cumsum(dim=-1) - 1
    assert not torch.equal(out["position_ids"], cumsum_positions)


def test_valid_position_ids_preserved() -> None:
    input_ids = torch.tensor([[1, 2]], dtype=torch.long)
    supplied = torch.tensor([[9, 8]], dtype=torch.long)
    out = apply_seneca_onnx_position_ids_compat(
        {"input_ids": input_ids, "position_ids": supplied},
        required_onnx_inputs={"input_ids", "position_ids"},
    )
    assert out["position_ids"] is supplied


def test_load_kwargs_and_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    graph = tmp_path / "onnx" / "model.onnx"
    graph.parent.mkdir(parents=True)
    graph.write_bytes(b"fake")
    captured: dict[str, object] = {}

    class FakeST:
        def __init__(self, path, **kwargs):  # type: ignore[no-untyped-def]
            captured["path"] = path
            captured["kwargs"] = kwargs
            self._mod = SimpleNamespace(forward=lambda **kw: kw)

        def __getitem__(self, idx):  # type: ignore[no-untyped-def]
            return SimpleNamespace(auto_model=self._mod)

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            captured["encode"] = kwargs
            import numpy as np

            if isinstance(texts, str):
                return np.ones(1024, dtype=np.float32)
            return np.ones((len(texts), 1024), dtype=np.float32)

    monkeypatch.setattr(
        "sentence_transformers.SentenceTransformer",
        FakeST,
    )
    captured_compat: dict[str, object] = {}

    def _fake_compat(model, *, required_onnx_inputs):  # type: ignore[no-untyped-def]
        captured_compat["required_onnx_inputs"] = list(required_onnx_inputs)
        return {"adapter_installed": True}

    monkeypatch.setattr(
        "offline_rag.dense.onnx_embedder.install_seneca_onnx_position_ids_compat",
        _fake_compat,
    )
    # Ensure constants match contract
    assert FROZEN_ORT_INTRA_OP_THREADS == 8
    assert FROZEN_ORT_INTER_OP_THREADS == 1
    assert FROZEN_ONNX_PROVIDER == "CPUExecutionProvider"

    emb = SentenceTransformersOnnxEmbedder(
        representation=_rep(tmp_path),
        model_id="Qwen/Qwen3-Embedding-0.6B",
        model_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
    )
    docs = emb.embed_documents(["a", "b"])
    assert len(docs) == 2
    assert len(docs[0]) == 1024
    assert captured["encode"]["batch_size"] == 32
    assert captured["encode"]["normalize_embeddings"] is True
    q = emb.embed_query("q")
    assert len(q) == 1024
    assert "prompt_name" not in captured["encode"]
    kw = captured["kwargs"]
    assert kw["backend"] == "onnx"
    assert kw["device"] == "cpu"
    assert kw["local_files_only"] is True
    assert kw["trust_remote_code"] is False
    model_kwargs = kw["model_kwargs"]
    assert model_kwargs["provider"] == "CPUExecutionProvider"
    assert model_kwargs["file_name"] == "onnx/model.onnx"
    assert model_kwargs["session_options"].intra_op_num_threads == 8
    assert model_kwargs["session_options"].inter_op_num_threads == 1
    assert captured_compat["required_onnx_inputs"] == [
        "input_ids",
        "attention_mask",
        "position_ids",
    ]


def test_no_production_onnx_graph_import() -> None:
    import offline_rag.dense.onnx_embedder as mod

    assert not hasattr(mod, "onnx_graph_input_names")
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import onnx\n" not in source
    assert "import onnx " not in source
    assert "from onnx " not in source
    assert "onnx.load" not in source
    # onnxruntime remains allowed for SessionOptions / CPUExecutionProvider.


def test_wrong_dimension_and_nonfinite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx" / "model.onnx").write_bytes(b"x")

    class FakeST:
        def __init__(self, *a, **k):  # type: ignore[no-untyped-def]
            pass

        def __getitem__(self, idx):  # type: ignore[no-untyped-def]
            return SimpleNamespace(auto_model=SimpleNamespace(forward=lambda **kw: kw))

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            import numpy as np

            return np.ones(4, dtype=np.float32)

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeST)
    monkeypatch.setattr(
        "offline_rag.dense.onnx_embedder.install_seneca_onnx_position_ids_compat",
        lambda *a, **k: {},
    )
    emb = SentenceTransformersOnnxEmbedder(
        representation=_rep(tmp_path),
        model_id="m",
        model_revision="r",
    )
    with pytest.raises(OnnxEmbedderError, match="dimension"):
        emb.embed_query("q")

    class NanST(FakeST):
        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            import numpy as np

            return np.array([float("nan")] * 1024, dtype=np.float32)

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", NanST)
    emb2 = SentenceTransformersOnnxEmbedder(
        representation=_rep(tmp_path),
        model_id="m",
        model_revision="r",
    )
    with pytest.raises(OnnxEmbedderError, match="non-finite"):
        emb2.embed_query("q")
