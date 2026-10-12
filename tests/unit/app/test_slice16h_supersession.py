"""16H Family E — source supersession isolation (non-vacuous).

Proves OLD_VERSION_UNIQUE_MARKER is absent from current vault content, dense
candidates, lexical candidates, reranker input, assembled context, citations /
generator evidence context after Replace publishes N+1. source_id remains stable.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.query import run_workspace_query
from offline_rag.app.query_binding import build_snapshot_query_binding
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.snapshot import PublishedPointer
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.protocol import GeneratorRequest
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.lexical.retrieve import LexicalRetriever
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
OLD_VERSION_UNIQUE_MARKER = "OLD_VERSION_UNIQUE_MARKER"
NEW_VERSION_UNIQUE_MARKER = "NEW_VERSION_UNIQUE_MARKER"
V2_ABSTAIN = json.dumps(
    {
        "abstain": True,
        "blocks": [],
        "abstention_reason": "insufficient_support",
    }
)


class _Closeable:
    def close(self) -> None:
        return None


def _provision(settings: AppSettings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


@contextmanager
def _client(
    tmp_path: Path,
    *,
    response_fn,
    reranker: FakeReranker,
) -> Iterator[tuple[TestClient, ApplicationRuntime]]:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    reranker_cfg = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    settings = settings.model_copy(
        update={"generation": generation, "reranker": reranker_cfg}
    )
    _provision(settings)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    generator = FakeGenerator(response_fn=response_fn)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: reranker,
            generator_client=lambda _s: generator,
            qdrant=_qdrant,
        ),
    )
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client, runtime


def _wait(client: TestClient, op_id: str) -> dict:
    deadline = time.time() + 60
    while time.time() < deadline:
        body = client.get(f"/v1/operations/{op_id}").json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise AssertionError("operation timeout")


def _active_blob(settings: AppSettings, workspace_id: str) -> str:
    record = WorkspaceStore(settings).get(workspace_id)
    vault = RawSourceVault(settings.paths.workspaces)
    parts: list[str] = []
    for source in record.sources:
        if not source.active:
            continue
        parts.append(
            vault.load_bytes(workspace_id, source.vault_object_id).decode(
                "utf-8", errors="ignore"
            )
        )
    return "\n".join(parts)


def test_slice16h_replace_keeps_source_id_and_excludes_old_marker(
    tmp_path: Path,
) -> None:
    presented: list[str] = []
    assembled: list = []
    generator_requests: list[GeneratorRequest] = []
    original_assemble = HybridRerankContextAssembler.assemble

    def recording_assemble(self, *args, **kwargs):
        ctx = original_assemble(self, *args, **kwargs)
        assembled.append(ctx)
        return ctx

    class _RecordingReranker(FakeReranker):
        def score_pairs(self, pairs):
            for pair in pairs:
                presented.append(getattr(pair, "passage_text", "") or "")
            return super().score_pairs(pairs)

    def _capture(request: GeneratorRequest) -> str:
        generator_requests.append(request)
        return V2_ABSTAIN

    HybridRerankContextAssembler.assemble = recording_assemble  # type: ignore[method-assign]
    try:
        with _client(
            tmp_path, response_fn=_capture, reranker=_RecordingReranker()
        ) as (client, runtime):
            created = client.post(
                "/v1/workspaces",
                json={"title": "16H supersession", "description": ""},
                headers={"Idempotency-Key": "16h-ss-ws"},
            )
            assert created.status_code == 201, created.text
            wid = created.json()["workspace_id"]

            v_old = f"{OLD_VERSION_UNIQUE_MARKER} valve torque procedure vN.\n".encode()
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "16h-ss-add", "If-Match": '"1"'},
                files={"files": ("manual_vN.txt", v_old, "text/plain")},
            )
            assert add.status_code == 202, add.text
            t0 = _wait(client, add.json()["operation_id"])
            assert t0["status"] == "succeeded"
            snap_n = t0["result"]["snapshot_id"]
            sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
            assert len(sources) == 1
            source_id = sources[0]["source_id"]
            version_n = sources[0]["version"]
            old_doc = sources[0]["document_id"]
            content_n = client.get(f"/v1/workspaces/{wid}/sources/{source_id}/content")
            assert content_n.status_code == 200
            assert OLD_VERSION_UNIQUE_MARKER.encode() in content_n.content

            # Confirm N is current evidence via query binding snapshot.
            q_n = client.post(
                f"/v1/workspaces/{wid}/query",
                json={"question": "What valve torque procedure is documented?"},
            )
            assert q_n.status_code == 200, q_n.text
            assert q_n.json()["snapshot_id"] == snap_n

            ws = client.get(f"/v1/workspaces/{wid}").json()
            v_new = (
                f"{NEW_VERSION_UNIQUE_MARKER} valve torque procedure vN1 revised.\n"
            ).encode()
            replace = client.put(
                f"/v1/workspaces/{wid}/sources/{source_id}",
                headers={
                    "Idempotency-Key": "16h-ss-repl",
                    "If-Match": f'"{ws["revision"]}"',
                },
                files={"files": ("manual_vN1.txt", v_new, "text/plain")},
            )
            assert replace.status_code == 202, replace.text
            t1 = _wait(client, replace.json()["operation_id"])
            assert t1["status"] == "succeeded", t1
            snap_n1 = t1["result"]["snapshot_id"]
            assert snap_n1 != snap_n

            ws2 = client.get(f"/v1/workspaces/{wid}").json()
            assert ws2["current_snapshot_id"] == snap_n1
            sources2 = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
            assert len(sources2) == 1
            assert sources2[0]["source_id"] == source_id
            assert sources2[0]["version"] == version_n + 1
            assert sources2[0]["document_id"] != old_doc
            new_doc = sources2[0]["document_id"]

            content = client.get(f"/v1/workspaces/{wid}/sources/{source_id}/content")
            assert content.status_code == 200
            assert OLD_VERSION_UNIQUE_MARKER.encode() not in content.content
            assert NEW_VERSION_UNIQUE_MARKER.encode() in content.content

            blob = _active_blob(runtime.settings, wid)
            assert OLD_VERSION_UNIQUE_MARKER not in blob
            assert NEW_VERSION_UNIQUE_MARKER in blob

            record = WorkspaceStore(runtime.settings).get(wid)
            pointer = current_pointer_path(
                runtime.settings.paths.corpora, record.backing_corpus_name
            )
            assert pointer.exists()
            published = PublishedPointer.model_validate_json(
                pointer.read_text(encoding="utf-8")
            )
            assert published.snapshot_id == snap_n1

            snap = runtime.publication.resolve(record.backing_corpus_name)
            binding = build_snapshot_query_binding(runtime.settings, snap)
            corpus_ids = set(binding.source_name_by_document_id().keys())
            assert old_doc not in corpus_ids
            assert new_doc in corpus_ids

            dense = DenseRetriever(
                runtime.settings,
                embedder=runtime.resources.embedder,
                backend=runtime.resources.qdrant,
            )
            dens = dense.retrieve(
                query=(
                    f"{OLD_VERSION_UNIQUE_MARKER} {NEW_VERSION_UNIQUE_MARKER} "
                    "valve torque"
                ),
                corpus_name=record.backing_corpus_name,
                top_k=20,
                index_id=binding.dense_index_id,
                collection_name=binding.dense_collection_name,
                chunk_set_id=binding.chunk_set_id,
            )
            dense_docs = {c.document_id for c in dens.candidates}
            dense_text = " ".join(getattr(c, "text", "") or "" for c in dens.candidates)
            assert old_doc not in dense_docs
            assert OLD_VERSION_UNIQUE_MARKER not in dense_text

            lexical = LexicalRetriever(runtime.settings)
            lex = lexical.retrieve(
                query=OLD_VERSION_UNIQUE_MARKER,
                corpus_name=record.backing_corpus_name,
                top_k=20,
                index_id=binding.lexical_index_id,
                chunk_set_id=binding.chunk_set_id,
            )
            lex_docs = {c.document_id for c in lex.candidates}
            lex_text = " ".join(getattr(c, "text", "") or "" for c in lex.candidates)
            assert old_doc not in lex_docs
            assert OLD_VERSION_UNIQUE_MARKER not in lex_text

            presented_before = len(presented)
            assembled_before = len(assembled)
            gen_before = len(generator_requests)
            outcome = run_workspace_query(
                runtime,
                workspace_id=wid,
                question=(
                    f"What valve torque procedure does {NEW_VERSION_UNIQUE_MARKER} "
                    f"document? Do not use superseded {OLD_VERSION_UNIQUE_MARKER}."
                ),
            )
            packed = json.dumps(outcome.as_dict())
            assert outcome.snapshot_id == record.current_snapshot_id
            assert old_doc not in packed
            assert OLD_VERSION_UNIQUE_MARKER not in packed or outcome.status != "answered"

            new_presentations = presented[presented_before:]
            assert new_presentations, "reranker must receive passages"
            assert all(OLD_VERSION_UNIQUE_MARKER not in text for text in new_presentations)

            new_contexts = assembled[assembled_before:]
            assert new_contexts, "bound query must assemble context"
            assert any(ctx.evidence_units for ctx in new_contexts)
            for ctx in new_contexts:
                assert OLD_VERSION_UNIQUE_MARKER not in (ctx.assembled_text or "")
                for unit in ctx.evidence_units:
                    assert OLD_VERSION_UNIQUE_MARKER not in unit.text
                    assert unit.document_id != old_doc

            new_reqs = generator_requests[gen_before:]
            assert new_reqs, "bound query must invoke generator"
            for req in new_reqs:
                blob_msg = "\n".join(m.content for m in req.messages)
                evidence_start = blob_msg.find("EVIDENCE:")
                assert evidence_start >= 0
                evidence_blob = blob_msg[evidence_start:]
                assert OLD_VERSION_UNIQUE_MARKER not in evidence_blob
                assert old_doc not in evidence_blob
    finally:
        HybridRerankContextAssembler.assemble = original_assemble  # type: ignore[method-assign]
