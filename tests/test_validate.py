"""Tests de la brique de validation (jeu borné + summarize + segments)."""

from decimal import Decimal

from nyris.strategy.backtest import summarize
from nyris.strategy.validate import variants_1h, variants_4h


def test_jeu_de_variantes_borne():
    v = variants_4h()
    names = [n for n, _ in v]
    assert "baseline" in names
    assert "trend100" in names
    assert "cand_active" in names
    # jeu volontairement borné (pas un grid massif)
    assert 8 <= len(v) <= 12
    base = dict(v)["baseline"]
    assert base.ema_trend == 200 and base.ema_fast == 20 and base.ema_slow == 50


def test_variantes_1h():
    assert {n for n, _ in variants_1h()} == {"baseline_1h", "cand_active_1h"}


def test_summarize_basique():
    trades = [
        {"pnl_net": "100", "r_multiple": 2.0, "bars": 10, "reason": "exit_take_profit",
         "entry_time": 0, "exit_time": 1},
        {"pnl_net": "-50", "r_multiple": -1.0, "bars": 5, "reason": "exit_stop",
         "entry_time": 2, "exit_time": 3},
    ]
    s = summarize(trades, Decimal("1000"), 30 * 24 * 3600 * 1000, 4.0)
    assert s["n_trades"] == 2
    assert s["win_rate"] == 0.5
    assert s["profit_factor"] == 2.0  # 100 / 50
    assert s["avg_r"] == 0.5
    assert s["exit_reason_distribution"] == {"exit_take_profit": 1, "exit_stop": 1}


def test_summarize_vide():
    s = summarize([], Decimal("1000"), 1000, 4.0)
    assert s["n_trades"] == 0
    assert s["profit_factor"] is None
    assert s["win_rate"] == 0.0
