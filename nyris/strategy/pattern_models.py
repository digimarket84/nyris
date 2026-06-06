"""Config et types du runner PATTERN (bidirectionnel : long ET short).

Deux schémas déterministes : cassure de range (Donchian) et pullback EMA (continuation).
Indépendant du baseline et du short ; réutilise Snapshot/Action de strategy.models.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal

from nyris.strategy.models import Action, Snapshot


class PatternReason(enum.StrEnum):
    skip_no_data = "skip_no_data"
    hold_no_pattern = "hold_no_pattern"
    hold_in_position = "hold_in_position"
    enter_long_breakout = "enter_long_breakout"
    enter_short_breakdown = "enter_short_breakdown"
    enter_long_pullback = "enter_long_pullback"
    enter_short_pullback = "enter_short_pullback"
    exit_stop = "exit_stop"
    exit_take_profit = "exit_take_profit"
    skip_blocked_max_positions = "skip_blocked_max_positions"
    skip_blocked_exposure = "skip_blocked_exposure"
    skip_blocked_cooldown = "skip_blocked_cooldown"
    skip_blocked_min_notional = "skip_blocked_min_notional"
    skip_blocked_volatility = "skip_blocked_volatility"


@dataclass(frozen=True)
class PatternParams:
    # Majors BTC/ETH/SOL retirés TEMPORAIREMENT (les pires au profil : -7€, 22% win).
    # Réversible : les remettre dans le tuple.
    universe: tuple[str, ...] = (
        "NEAR", "SUI", "LINK", "AVAX", "DOGE", "PEPE",
        "POND", "BABY", "HOME", "LA",
    )
    timeframe: str = "5m"  # détection
    donchian_lookback: int = 20  # fenêtre cassure (plus_haut/plus_bas)
    ema_trend: int = 200  # filtre de tendance (pullback)
    ema_pullback: int = 20  # EMA de repli
    atr_period: int = 14
    atr_stop_mult: float = 1.5
    reward_r: float = 2.0
    max_stop_pct: float = 0.03
    cooldown: int = 2
    min_atr_pct: float = 0.0008
    max_atr_pct: float = 0.012
    starting_capital: Decimal = Decimal("50")
    position_fraction: Decimal = Decimal("0.5")  # 25 € / trade
    max_open_positions: int = 3
    max_total_exposure: Decimal = Decimal("1.5")
    min_notional: Decimal = Decimal("10")
    commission_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    funding_rate_daily: Decimal = Decimal("0.0003")
    run_id: str = "live-pattern-v1"

    def key(self) -> str:
        return (
            f"pat-t{self.timeframe}_dc{self.donchian_lookback}"
            f"_et{self.ema_trend}_ep{self.ema_pullback}"
            f"_R{self.reward_r}_sl{self.atr_stop_mult}"
        )


@dataclass(frozen=True)
class PatternPosition:
    side: str  # long / short
    entry: Decimal
    stop: Decimal
    take_profit: Decimal
    bars_held: int = 0


@dataclass(frozen=True)
class PatternDecision:
    action: Action
    reason: PatternReason
    snapshot: Snapshot
    side: str | None = field(default=None)
    pattern: str | None = field(default=None)
    entry: Decimal | None = field(default=None)
    stop: Decimal | None = field(default=None)
    take_profit: Decimal | None = field(default=None)
