"""Config et taxonomie du runner SHORT (indépendant du baseline)."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal


class ShortReason(enum.StrEnum):
    skip_no_data = "skip_no_data"
    hold_no_downtrend = "hold_no_downtrend"  # à plat : pas de tendance baissière
    hold_no_setup = "hold_no_setup"  # baissier mais pas de rejet
    hold_in_position = "hold_in_position"
    enter_short_signal = "enter_short_signal"
    exit_short_stop = "exit_short_stop"
    exit_short_take_profit = "exit_short_take_profit"
    exit_short_trend_recovered = "exit_short_trend_recovered"
    exit_short_time = "exit_short_time"
    skip_blocked_max_positions = "skip_blocked_max_positions"
    skip_blocked_exposure = "skip_blocked_exposure"
    skip_blocked_cooldown = "skip_blocked_cooldown"
    skip_blocked_min_notional = "skip_blocked_min_notional"


@dataclass(frozen=True)
class ShortParams:
    # Univers / horizon
    universe: tuple[str, ...] = ("BTC", "ETH", "SOL")
    timeframe: str = "4h"
    # Indicateurs
    ema_trend: int = 200
    ema_pullback: int = 20
    atr_period: int = 14
    # Sorties
    atr_stop_mult: float = 1.5
    reward_r: float = 1.5
    max_hold: int = 40
    max_stop_pct: float = 0.15
    cooldown: int = 3
    # Sizing (capital de référence 50 €, notional fixe non-compounding)
    starting_capital: Decimal = Decimal("50")
    position_fraction: Decimal = Decimal("0.5")  # 25 € par short
    max_open_positions: int = 1
    max_total_exposure: Decimal = Decimal("1.0")
    min_notional: Decimal = Decimal("10")
    # Coûts (par côté sauf funding qui est /jour)
    commission_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    funding_rate_daily: Decimal = Decimal("0.0003")
    # Identité (run_id court <= 40 caractères)
    run_id: str = "live-short-v1"

    def key(self) -> str:
        return (
            f"short-t{self.timeframe}_et{self.ema_trend}_p{self.ema_pullback}"
            f"_sl{self.atr_stop_mult}_R{self.reward_r}_h{self.max_hold}"
        )
