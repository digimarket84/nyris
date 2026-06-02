"""Tests de la brique de revalidation (config V1.1 + folds)."""

from decimal import Decimal

from nyris.strategy.revalidate import CONFIGS, fold_summaries


def test_config_v1_1():
    assert "v1_1" in CONFIGS and "baseline" in CONFIGS
    v = CONFIGS["v1_1"]
    assert v.timeframe == "4h"
    assert v.ema_trend == 200 and v.ema_fast == 20 and v.ema_slow == 50
    assert v.atr_stop_mult == 1.5 and v.reward_r == 1.5 and v.max_hold == 60
    # baseline = défauts
    b = CONFIGS["baseline"]
    assert b.atr_stop_mult == 2.0 and b.reward_r == 2.0


def test_fold_summaries_partition():
    trades = [
        {"pnl_net": "10", "r_multiple": 1.0, "bars": 1, "reason": "exit_take_profit",
         "entry_time": t, "exit_time": t + 1}
        for t in [0, 10, 20, 30, 40, 50]
    ]
    folds = fold_summaries(trades, 0, 60, 3, Decimal("3000"), 4.0)
    assert len(folds) == 3
    assert sum(f["n_trades"] for f in folds) == 6  # partition exacte
    assert [f["fold"] for f in folds] == [1, 2, 3]


def test_fold_summaries_vide():
    folds = fold_summaries([], 0, 60, 3, Decimal("3000"), 4.0)
    assert all(f["n_trades"] == 0 for f in folds)
