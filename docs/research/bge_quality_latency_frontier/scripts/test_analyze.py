"""Regression checks for prefix membership and padding accounting."""

import pytest
from analyze import padding, replay


def test_replay_filters_by_original_input_prefix():
    fused = [str(i) for i in range(30)]
    result = replay(fused, fused, fused[::-1])
    assert result["BGE-5"] == ["4", "3", "2", "1", "0"]
    assert result["BGE-30"] == fused[::-1]
    assert result["RRF"] == fused


@pytest.mark.parametrize("change", ["pool_order", "rank_count", "rank_member"])
def test_replay_rejects_invalid_permutation(change):
    fused = [str(i) for i in range(30)]
    pool = fused.copy()
    ranked = fused[::-1]
    if change == "pool_order":
        pool.reverse()
    elif change == "rank_count":
        ranked.pop()
    else:
        ranked[-1] = ranked[0]
    with pytest.raises(ValueError, match="incomplete or inconsistent"):
        replay(fused, pool, ranked)


def test_padding_uses_batch_max_width():
    result = padding([1, 3, 4], [[1, 3], [4]])
    assert result["slots"] == 10
    assert result["padding"] == 2
    assert result["attention_proxy"] == 34
