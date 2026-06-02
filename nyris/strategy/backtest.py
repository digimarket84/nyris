"""Harness de backtest déterministe (mono-actif), O(n).

Rejoue la décision sur l'historique (indicateurs précalculés une fois), gère une
position à la fois, applique les frais via `services.pnl`, calcule les métriques.
Exécution : python -m nyris.strategy.backtest BTC [timeframe] [limit]
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from nyris.services import pnl
from nyris.strategy.engine import _decide, compute_indicators, warmup
from nyris.strategy.models import Action, Candle, PositionState, StrategyParams

_MS_PER_MONTH = 1000 * 60 * 60 * 24 * 30


def timeframe_hours(tf: str) -> float:
    tf = tf.strip().lower()
    if tf.endswith("h"):
        return float(int(tf[:-1]))
    if tf.endswith("d"):
        return float(int(tf[:-1]) * 24)
    if tf.endswith("m"):
        return float(int(tf[:-1]) / 60)
    return 1.0


def summarize(
    trades: list[dict], starting_capital: Decimal, span_ms: float, tf_hours: float
) -> dict:
    """Métriques à partir d'une liste de trades (réutilisable validation/segments)."""
    n = len(trades)
    pnls = [Decimal(t["pnl_net"]) for t in trades]
    wins = [p for p in pnls if p > 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum((-p for p in pnls if p < 0), Decimal("0"))
    r_vals = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    bars = [t["bars"] for t in trades]

    cap = Decimal(starting_capital)
    peak = cap
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x["exit_time"]):
        cap += Decimal(t["pnl_net"])
        if cap > peak:
            peak = cap
        if peak > 0:
            max_dd = max(max_dd, float((peak - cap) / peak))

    total_pnl = sum(pnls, Decimal("0"))
    months = (span_ms / _MS_PER_MONTH) if span_ms and span_ms > 0 else None
    return {
        "n_trades": n,
        "trades_per_month": round(n / months, 2) if months else None,
        "win_rate": round(len(wins) / n, 4) if n else 0.0,
        "profit_factor": round(float(gross_profit / gross_loss), 4) if gross_loss > 0 else None,
        "avg_r": round(sum(r_vals) / len(r_vals), 4) if r_vals else None,
        "total_pnl": str(total_pnl),
        "total_return_pct": (
            round(float(total_pnl / Decimal(starting_capital) * 100), 4)
            if starting_capital
            else 0.0
        ),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "avg_bars_in_position": round(sum(bars) / len(bars), 2) if bars else None,
        "avg_duration_hours": round((sum(bars) / len(bars)) * tf_hours, 2) if bars else None,
        "exit_reason_distribution": dict(Counter(t["reason"] for t in trades)),
    }


@dataclass
class BacktestResult:
    params: dict
    starting_capital: Decimal
    final_capital: Decimal
    metrics: dict
    open_position: bool
    trades: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "params": self.params,
            "starting_capital": str(self.starting_capital),
            "final_capital": str(self.final_capital),
            "open_position": self.open_position,
            "trades": self.trades[-10:],
        }
        d.update(self.metrics)
        return d


def run_backtest(
    candles: list[Candle],
    params: StrategyParams,
    starting_capital: Decimal = Decimal("1000"),
    compounding: bool = True,
) -> BacktestResult:
    cap = starting_capital
    position: dict | None = None
    entry_index: int | None = None
    cooldown_until = -1
    trades: list[dict] = []

    warm = warmup(params)
    ef, es, et, at = compute_indicators(candles, params)

    for i in range(warm, len(candles)):
        pos_state = None
        if position is not None:
            pos_state = PositionState(
                entry_price=position["entry"],
                stop=position["stop"],
                take_profit=position["tp"],
                bars_held=i - entry_index,
            )
        dec = _decide(i, ef, es, et, at, candles, pos_state, params)

        if position is None:
            if dec.action == Action.enter and i > cooldown_until:
                base = cap if compounding else starting_capital
                notional = (base * params.position_fraction).quantize(Decimal("0.01"))
                er = pnl.compute_entry(notional, dec.entry, params.entry_fee_rate)
                risk_eur = (er.quantity * (dec.entry - dec.stop)).quantize(Decimal("0.01"))
                position = {
                    "entry": dec.entry,
                    "stop": dec.stop,
                    "tp": dec.take_profit,
                    "qty": er.quantity,
                    "notional": notional,
                    "risk_eur": risk_eur,
                    "entry_time": candles[i].close_time,
                }
                entry_index = i
        elif dec.action == Action.exit:
            cr = pnl.compute_close(
                position["notional"], position["qty"], dec.snapshot.close, params.exit_fee_rate
            )
            cap = cap + cr.pnl_net
            r_mult = float(cr.pnl_net / position["risk_eur"]) if position["risk_eur"] != 0 else None
            trades.append(
                {
                    "entry_time": position["entry_time"],
                    "exit_time": candles[i].close_time,
                    "bars": i - entry_index,
                    "entry": str(position["entry"]),
                    "exit": str(dec.snapshot.close),
                    "pnl_net": str(cr.pnl_net),
                    "pnl_percent": str(cr.pnl_percent),
                    "r_multiple": None if r_mult is None else round(r_mult, 3),
                    "reason": dec.reason.value,
                }
            )
            cooldown_until = i + params.cooldown
            position = None
            entry_index = None

    span = candles[-1].close_time - candles[warm].close_time if len(candles) > warm else 0
    metrics = summarize(trades, starting_capital, span, timeframe_hours(params.timeframe))
    return BacktestResult(
        params=params.to_dict(),
        starting_capital=starting_capital,
        final_capital=cap,
        metrics=metrics,
        open_position=position is not None,
        trades=trades,
    )


def _main() -> None:
    import json
    import sys

    from nyris.services import candles as candles_service

    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "4h"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    params = StrategyParams(timeframe=timeframe)

    candles = candles_service.get_candles(f"{symbol}EUR", timeframe, limit)
    result = run_backtest(candles, params)
    print(f"# Backtest {symbol}EUR {timeframe} ({len(candles)} bougies)")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
