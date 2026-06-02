"""Tests du harness de backtest (déterminisme + sérialisation + métriques)."""

import json
import math
from decimal import Decimal

from nyris.strategy.backtest import run_backtest, timeframe_hours
from nyris.strategy.models import Candle, StrategyParams

_STEP = 4 * 3600 * 1000

P = StrategyParams(
    ema_fast=2, ema_slow=3, ema_trend=5, atr_period=3, max_hold=10, timeframe="4h"
)


def mk(closes):
    out = []
    for idx, c in enumerate(closes):
        cd = Decimal(str(round(c, 4)))
        out.append(
            Candle(
                open_time=idx * _STEP,
                close_time=(idx + 1) * _STEP,
                open=cd,
                high=Decimal(str(round(c + 1, 4))),
                low=Decimal(str(round(c - 1, 4))),
                close=cd,
                volume=Decimal("1"),
            )
        )
    return out


def test_timeframe_hours():
    assert timeframe_hours("4h") == 4.0
    assert timeframe_hours("1h") == 1.0
    assert timeframe_hours("1d") == 24.0


def test_backtest_deterministe_et_serialisable():
    # série oscillante haussière déterministe
    closes = [100 + i * 0.5 + 5 * math.sin(i / 3.0) for i in range(90)]
    candles = mk(closes)
    r1 = run_backtest(candles, P, Decimal("1000")).to_dict()
    r2 = run_backtest(candles, P, Decimal("1000")).to_dict()
    assert r1 == r2  # mêmes données => même résultat
    json.dumps(r1)  # sérialisable
    assert r1["n_trades"] >= 1
    for key in ["win_rate", "profit_factor", "trades_per_month",
                "avg_duration_hours", "exit_reason_distribution"]:
        assert key in r1
    # somme des raisons de sortie == nombre de trades
    assert sum(r1["exit_reason_distribution"].values()) == r1["n_trades"]
