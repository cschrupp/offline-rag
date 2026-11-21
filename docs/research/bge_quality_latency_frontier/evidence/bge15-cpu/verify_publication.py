"""Check separate depth identities using the existing offline publication fixture."""

import argparse
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from offline_rag.app.errors import AppError
from offline_rag.app.publication import (
    ProductPublicationRegistry,
    snapshot_manifest_path,
)
from offline_rag.app.snapshot import compute_snapshot_id
from offline_rag.config.models import RerankerSettings
from offline_rag.rerank.config_hash import build_reranker_config_hash


def verify(tokenizer_artifacts):
    root = Path(__file__).resolve().parents[5]
    fixture_path = root / "tests/unit/app/test_slice15c_snapshots_leases_documents.py"
    spec = importlib.util.spec_from_file_location("publication_fixture", fixture_path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    fixture.TIKTOKEN_SRC = tokenizer_artifacts

    with TemporaryDirectory() as temporary:
        baseline = fixture._settings(Path(temporary))
        candidate_reranker = RerankerSettings.model_validate(
            baseline.reranker.model_dump() | {"input_k": 15}
        )
        candidate = baseline.model_copy(update={"reranker": candidate_reranker})
        assert baseline.reranker.input_k == 30 and baseline.reranker.output_k == 10
        assert candidate.reranker.output_k == 10 and candidate.context.anchor_k == 5
        manifest_a = fixture._write_scientific_stack(baseline)
        manifest_b = manifest_a.model_copy(
            update={"reranker_config_hash": build_reranker_config_hash(candidate)}
        )
        assert manifest_a.reranker_config_hash != manifest_b.reranker_config_hash
        assert compute_snapshot_id(manifest_a) != compute_snapshot_id(manifest_b)

        qdrant = fixture._FakeQdrant()
        qdrant.counts["col_ccc"] = 1
        a = ProductPublicationRegistry(baseline, qdrant=qdrant)
        b = ProductPublicationRegistry(candidate, qdrant=qdrant)
        corpus = "bge15-fixture"
        sid_a = a.publish(corpus, manifest_a)
        original_path = snapshot_manifest_path(baseline.paths.corpora, corpus, sid_a)
        original = original_path.read_bytes()
        sid_b = b.publish(corpus, manifest_b)

        original_bound = a.resolve_snapshot(corpus, sid_a)
        candidate_bound = b.resolve_snapshot(corpus, sid_b)
        assert (
            original_bound.identity.dense_index_id
            == candidate_bound.identity.dense_index_id
        )
        assert (
            original_bound.identity.lexical_index_id
            == candidate_bound.identity.lexical_index_id
        )
        assert original_path.read_bytes() == original
        for registry, incompatible in ((a, sid_b), (b, sid_a)):
            try:
                registry.resolve_snapshot(corpus, incompatible)
            except AppError as exc:
                assert exc.details["reason"] == "reranker_config_stale"
            else:
                raise AssertionError("mismatched depth resolved")

        assert a.publish(corpus, manifest_a) == sid_a
        assert a.resolve(corpus).snapshot_id == sid_a
        assert original_path.read_bytes() == original
        print(
            json.dumps(
                {
                    "fixture_only": True,
                    "different_reranker_hashes": True,
                    "different_snapshot_ids": True,
                    "same_dense_and_lexical_identity": True,
                    "cross_profile_resolution_rejected": 2,
                    "original_manifest_preserved": True,
                    "rollback_pointer_verified": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tokenizer_artifacts", type=Path)
    verify(parser.parse_args().tokenizer_artifacts)
