"""Compare the RRF and BGE ordering of identical fixed prefixes."""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from analyze import metrics, read, replay, verify_inputs

from offline_rag.evaluation.gold import load_gold_dataset

DEPTHS = (5, 10, 15, 20)
ENDPOINTS = ("ndcg5", "recall5", "precision5", "hit5")
DATA = Path(__file__).resolve().parents[1] / "data"


def compare_prefixes(case, fused, pool, ranked):
    orders = replay(fused, pool, ranked)
    comparison = {}
    for depth in DEPTHS:
        rrf = fused[:depth]
        bge = orders[f"BGE-{depth}"]
        before, after = metrics(case, rrf), metrics(case, bge)
        comparison[str(depth)] = {
            "delta": {m: after[m] - before[m] for m in ENDPOINTS},
            "rrf": {m: before[m] for m in ENDPOINTS},
            "bge": {m: after[m] for m in ENDPOINTS},
            "top5_order_changed": rrf[:5] != bge[:5],
            "top5_membership_changed": set(rrf[:5]) != set(bge[:5]),
        }
    return comparison


def outcome(delta):
    return "improved" if delta > 0 else "regressed" if delta < 0 else "tied"


def aggregate(rows):
    report = {}
    for depth in map(str, DEPTHS):
        arms = [row["depths"][depth] for row in rows]
        counts = Counter(outcome(a["delta"]["ndcg5"]) for a in arms)
        report[depth] = {
            "n": len(arms),
            "means": {
                key: {m: statistics.mean(a[key][m] for a in arms) for m in ENDPOINTS}
                for key in ("rrf", "bge", "delta")
            },
            "ndcg5_outcomes": {k: counts[k] for k in ("improved", "regressed", "tied")},
            "top5_order_changed": sum(a["top5_order_changed"] for a in arms),
            "top5_membership_changed": sum(a["top5_membership_changed"] for a in arms),
            "membership_changed_no_ndcg_gain": sum(
                a["top5_membership_changed"] and a["delta"]["ndcg5"] <= 0 for a in arms
            ),
            "membership_changed_all_endpoints_tied": sum(
                a["top5_membership_changed"]
                and all(delta == 0 for delta in a["delta"].values())
                for a in arms
            ),
        }
    return report


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(root, gold_path):
    expected = read(DATA / "historical-input-sha256.json")
    frozen_observations = read(DATA / "observations.json")
    (cohort_name,) = (
        name for name in expected if name.endswith("_adjudication_cohort_map_v1.json")
    )
    left, right = (
        root / "eval/results/9h_p" / name
        for name in ("E_hybrid_rrf_full22.json", "F_hybrid_rerank_full22.json")
    )
    cohort = root / "eval/fixtures/sufficiency" / cohort_name
    files = (left, right, cohort, gold_path / "meta.json", gold_path / "cases.jsonl")
    pins = {p.name: expected[p.name] for p in files}
    verify_inputs(files, pins)
    gold = load_gold_dataset(gold_path)
    rrf, bge, membership_doc = map(read, (left, right, cohort))
    for artifact in (rrf, bge):
        require(
            (
                artifact["gold_dataset_id"],
                artifact["corpus_id"],
                artifact["chunk_set_id"],
            )
            == (gold.dataset_id, gold.meta.corpus_id, gold.meta.chunk_set_id),
            "artifact identity mismatch",
        )
    for key in ("dense_index_id", "lexical_index_id", "fusion_config_hash"):
        require(
            rrf["semantic_provenance"][key] == bge["semantic_provenance"][key],
            "source index or fusion mismatch",
        )
    require(
        membership_doc["gold_dataset_id"] == gold.dataset_id, "cohort identity mismatch"
    )
    membership = {r["case_id"]: r["label_cohort"] for r in membership_doc["cases"]}
    a, b = ({r["case_id"]: r for r in arm["cases"]} for arm in (rrf, bge))
    require(
        set(a) == set(b) == set(membership) == {c.id for c in gold.cases},
        "cohort membership mismatch",
    )
    require(
        len(a)
        == len(rrf["cases"])
        == len(bge["cases"])
        == len(membership_doc["cases"]),
        "duplicate cases",
    )
    rows = []
    for number, case in enumerate(sorted(gold.cases, key=lambda case: case.id), 1):
        ar, br = a[case.id], b[case.id]
        positives = {j.chunk_id for j in case.judgments}
        require(
            case.quality_eligible
            and all(
                x["error"] is None
                and x["query"] == case.query
                and set(x["relevant_chunk_ids"]) == positives
                for x in (ar, br)
            ),
            "invalid case or mismatched judgments",
        )
        rows.append(
            {
                "ordinal": number,
                "category": case.category,
                "cohort": membership[case.id],
                "depths": compare_prefixes(
                    case,
                    ar["retrieved_chunk_ids"],
                    br["diagnostics"]["input_pool_chunk_ids"],
                    br["retrieved_chunk_ids"],
                ),
            }
        )
    human = [row for row in rows if row["cohort"] == "human_reviewed"]
    assistant = [row for row in rows if row["cohort"] == "assistant_only"]
    require(
        (len(human), len(assistant), len(rows)) == (16, 6, 22), "unexpected cohort size"
    )
    require(
        frozen_observations["provenance"]["gold"] == gold.dataset_id,
        "historical study mismatch",
    )
    categories = {}
    for category in sorted({r["category"] for r in human}):
        subset = [r for r in human if r["category"] == category]
        categories[category] = {
            "n": len(subset),
            "depth10_ndcg5_outcomes": dict(
                Counter(outcome(r["depths"]["10"]["delta"]["ndcg5"]) for r in subset)
            ),
        }
    return {
        "input_sha256": pins,
        "gold": gold.dataset_id,
        "corpus": gold.meta.corpus_id,
        "chunk_set": gold.meta.chunk_set_id,
        "rrf_run": rrf["run_id"],
        "bge_run": bge["run_id"],
        "rows": rows,
        "human_reviewed": aggregate(human),
        "assistant_only": aggregate(assistant),
        "all": aggregate(rows),
        "human_reviewed_categories": categories,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_repo", type=Path)
    parser.add_argument("gold_dataset", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(run(args.artifact_repo, args.gold_dataset), indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
