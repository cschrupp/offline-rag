"""Targeted matched-prefix replay regressions."""

from small_pool import aggregate, compare_prefixes

from offline_rag.evaluation.gold import GoldCase


def test_matched_prefix_can_reorder_without_replacing_at_five():
    fused = [str(number) for number in range(30)]
    case = GoldCase.model_validate(
        {
            "id": "case",
            "query": "synthetic",
            "judgments": [{"chunk_id": "4", "relevance": 2}],
        }
    )
    reversed_rank = list(reversed(fused))
    depths = compare_prefixes(case, fused, fused, reversed_rank)
    assert depths["5"]["top5_order_changed"]
    assert not depths["5"]["top5_membership_changed"]
    assert depths["5"]["delta"]["ndcg5"] > 0
    assert depths["5"]["delta"]["recall5"] == 0
    assert depths["10"]["top5_membership_changed"]
    assert depths["10"]["delta"]["recall5"] == -1
    report = aggregate([{"depths": depths}])
    assert report["10"]["ndcg5_outcomes"]["regressed"] == 1
    assert report["10"]["membership_changed_no_ndcg_gain"] == 1
