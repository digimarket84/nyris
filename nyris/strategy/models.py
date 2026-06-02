"""Modèles de la stratégie : bougie, paramètres, position, décision.

Tout est sérialisable proprement (Decimal -> str, enum -> value) pour préparer
plus tard la table `strategy_decisions` sans refonte.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal


class Action(enum.StrEnum):
    enter = "enter"
    exit = "exit"
    hold = "hold"
    skip = "skip"


class Reason(enum.StrEnum):
    # Taxonomie normalisée à préfixes : skip_ / hold_ / enter_ / exit_
    skip_no_data = "skip_no_data"
    hold_no_trend = "hold_no_trend"  # à plat : tendance de fond non haussière
    hold_no_cross = "hold_no_cross"  # à plat : tendance OK mais pas de croisement
    hold_in_position = "hold_in_position"  # en position : aucune sortie déclenchée
    enter_signal = "enter_signal"
    exit_stop = "exit_stop"
    exit_take_profit = "exit_take_profit"
    exit_inverse = "exit_inverse"
    exit_trend_invalidated = "exit_trend_invalidated"
    exit_time = "exit_time"
    # Entrée bloquée par un garde-fou du runner (signal valide mais non exécuté)
    skip_blocked_max_positions = "skip_blocked_max_positions"
    skip_blocked_exposure = "skip_blocked_exposure"
    skip_blocked_cooldown = "skip_blocked_cooldown"
    skip_blocked_min_notional = "skip_blocked_min_notional"


@dataclass(frozen=True)
class Candle:
    open_time: int  # ms epoch (ouverture)
    close_time: int  # ms epoch (clôture)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def from_binance(cls, row: list) -> Candle:
        return cls(
            open_time=int(row[0]),
            close_time=int(row[6]),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
        )


@dataclass(frozen=True)
class StrategyParams:
    # Univers / horizon
    universe: tuple[str, ...] = ("BTC", "ETH", "SOL")
    timeframe: str = "4h"
    # Indicateurs
    ema_fast: int = 20
    ema_slow: int = 50
    ema_trend: int = 200
    atr_period: int = 14
    # Sorties
    atr_stop_mult: float = 2.0
    reward_r: float = 2.0
    max_hold: int = 60
    max_stop_pct: float = 0.15  # le stop ne peut pas être plus loin que 15 %
    cooldown: int = 3
    # Sizing (utilisé par le backtest / l'engine, pas par evaluate)
    position_fraction: Decimal = Decimal("0.10")
    max_open_positions: int = 3
    max_total_exposure: Decimal = Decimal("0.50")
    # Frais
    entry_fee_rate: Decimal = Decimal("0.001")
    exit_fee_rate: Decimal = Decimal("0.001")

    def key(self) -> str:
        """Identifiant compact et lisible de la config (pour strategy_decisions)."""
        return (
            f"t{self.timeframe}_et{self.ema_trend}_{self.ema_fast}/{self.ema_slow}"
            f"_atr{self.atr_stop_mult}_R{self.reward_r}_h{self.max_hold}"
        )

    def to_dict(self) -> dict:
        return {
            "universe": list(self.universe),
            "timeframe": self.timeframe,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "ema_trend": self.ema_trend,
            "atr_period": self.atr_period,
            "atr_stop_mult": self.atr_stop_mult,
            "reward_r": self.reward_r,
            "max_hold": self.max_hold,
            "max_stop_pct": self.max_stop_pct,
            "cooldown": self.cooldown,
            "position_fraction": str(self.position_fraction),
            "max_open_positions": self.max_open_positions,
            "max_total_exposure": str(self.max_total_exposure),
            "entry_fee_rate": str(self.entry_fee_rate),
            "exit_fee_rate": str(self.exit_fee_rate),
        }


@dataclass(frozen=True)
class PositionState:
    entry_price: Decimal
    stop: Decimal
    take_profit: Decimal
    bars_held: int


def _dstr(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


@dataclass(frozen=True)
class Snapshot:
    candle_close_time: int
    close: Decimal
    ema_fast: Decimal | None
    ema_slow: Decimal | None
    ema_trend: Decimal | None
    atr: Decimal | None

    def to_dict(self) -> dict:
        return {
            "candle_close_time": self.candle_close_time,
            "close": _dstr(self.close),
            "ema_fast": _dstr(self.ema_fast),
            "ema_slow": _dstr(self.ema_slow),
            "ema_trend": _dstr(self.ema_trend),
            "atr": _dstr(self.atr),
        }


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: Reason
    snapshot: Snapshot
    entry: Decimal | None = field(default=None)
    stop: Decimal | None = field(default=None)
    take_profit: Decimal | None = field(default=None)

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason.value,
            "entry": _dstr(self.entry),
            "stop": _dstr(self.stop),
            "take_profit": _dstr(self.take_profit),
            "snapshot": self.snapshot.to_dict(),
        }
