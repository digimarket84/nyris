"""Harness de backtest déterministe (mono-actif).

Rejoue `evaluate()` sur l'historique de bougies, gère une position à la fois,
applique les frais via `services.pnl`, et calcule les métriques de validation.
Exécution : python -m nyris.strategy.backtest BTC [timeframe] [limit]
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from nyris.services import pnl
from nyris.strategy.engine import evaluate
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


@dataclass
class BacktestResult:
    params: dict
    starting_capital: Decimal
    final_capital: Decimal
    n_trades: int
    win_rate: float
    profit_factor: float | None
    avg_r: float | None
    total_pnl: Decimal
    total_return_pct: float
    max_drawdown_pct: float
    avg_bars_in_position: float | None
    avg_duration_hours: float | None
    trades_per_month: float | None
    exit_reason_distribution: dict
    open_position: bool
    trades: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "params": self.params,
            "starting_capital": str(self.starting_capital),
            "final_capital": str(self.final_capital),
            "n_trades": self.n_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": None if self.profit_factor is None else round(self.profit_factor, 4),
            "avg_r": None if self.avg_r is None else round(self.avg_r, 4),
            "total_pnl": str(self.total_pnl),
            "total_return_pct": round(self.total_return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "avg_bars_in_position": (
                None if self.avg_bars_in_position is None else round(self.avg_bars_in_position, 2)
            ),
            "avg_duration_hours": (
                None if self.avg_duration_hours is None else round(self.avg_duration_hours, 2)
            ),
            "trades_per_month": (
                None if self.trades_per_month is None else round(self.trades_per_month, 2)
            ),
            "exit_reason_distribution": self.exit_reason_distribution,
            "open_position": self.open_position,
            "trades": self.trades[-10:],  # derniers trades en exemple
        }


def run_backtest(
    candles: list[Candle],
    params: StrategyParams,
    starting_capital: Decimal = Decimal("1000"),
) -> BacktestResult:
    cap = starting_capital
    equity_peak = cap
    max_dd = 0.0
    position: dict | None = None
    entry_index: int | None = None
    cooldown_until = -1
    trades: list[dict] = []

    warmup = max(params.ema_trend, params.ema_slow, params.atr_period) + 2

    for i in range(warmup, len(candles)):
        window = candles[: i + 1]
        pos_state = None
        if position is not None:
            pos_state = PositionState(
                entry_price=position["entry"],
                stop=position["stop"],
                take_profit=position["tp"],
                bars_held=i - entry_index,
            )
        dec = evaluate(window, pos_state, params)

        if position is None:
            if dec.action == Action.enter and i > cooldown_until:
                notional = (cap * params.position_fraction).quantize(Decimal("0.01"))
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
            r_mult = (
                float(cr.pnl_net / position["risk_eur"]) if position["risk_eur"] != 0 else None
            )
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

        if cap > equity_peak:
            equity_peak = cap
        if equity_peak > 0:
            dd = float((equity_peak - cap) / equity_peak)
            if dd > max_dd:
                max_dd = dd

    # Métriques
    n = len(trades)
    wins = [t for t in trades if Decimal(t["pnl_net"]) > 0]
    gross_profit = sum((Decimal(t["pnl_net"]) for t in wins), Decimal("0"))
    gross_loss = sum(
        (-Decimal(t["pnl_net"]) for t in trades if Decimal(t["pnl_net"]) < 0), Decimal("0")
    )
    r_values = [t["r_multiple"] for t in trades if t["r_multiple"] is not None]
    bars = [t["bars"] for t in trades]
    tf_h = timeframe_hours(params.timeframe)

    months = None
    if len(candles) > warmup:
        span = candles[-1].close_time - candles[warmup].close_time
        months = max(span / _MS_PER_MONTH, 1e-9)

    return BacktestResult(
        params=params.to_dict(),
        starting_capital=starting_capital,
        final_capital=cap,
        n_trades=n,
        win_rate=(len(wins) / n) if n else 0.0,
        profit_factor=(float(gross_profit / gross_loss) if gross_loss > 0 else None),
        avg_r=(sum(r_values) / len(r_values) if r_values else None),
        total_pnl=cap - starting_capital,
        total_return_pct=float((cap / starting_capital - 1) * 100) if starting_capital else 0.0,
        max_drawdown_pct=max_dd * 100,
        avg_bars_in_position=(sum(bars) / len(bars) if bars else None),
        avg_duration_hours=((sum(bars) / len(bars)) * tf_h if bars else None),
        trades_per_month=(n / months if months else None),
        exit_reason_distribution=dict(Counter(t["reason"] for t in trades)),
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
