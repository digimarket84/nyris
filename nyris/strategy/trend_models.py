"""Config + types du runner TREND-FOLLOWING daily (long-only, Donchian).

Validé en Phase 1/1b (walk-forward + sweep + 7 ans) : edge robuste, surtout en
réduction de drawdown. Long spot uniquement -> pas de funding (carry = 0).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal


class TrendReason(enum.StrEnum):
    skip_no_data = "skip_no_data"
    hold_flat = "hold_flat"  # pas de cassure -> on reste hors marché
    hold_in_position = "hold_in_position"
    enter_trend_breakout = "enter_trend_breakout"
    exit_trend_down = "exit_trend_down"  # cassure du plus-bas Donchian de sortie


@dataclass(frozen=True)
class TrendParams:
    # Univers : majors + alts liquides à long historique (validés en backtest).
    universe: tuple[str, ...] = ("BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR", "DOGE")
    timeframe: str = "1d"
    donchian_entry: int = 100  # cassure du plus-haut N jours -> long
    donchian_exit: int = 50    # cassure du plus-bas M jours -> sortie
    per_position: Decimal = Decimal("100")  # notional € par actif (paper)
    commission_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    funding_rate_daily: Decimal = Decimal("0")  # long spot -> pas de portage
    run_id: str = "live-trend-v1"

    def key(self) -> str:
        return f"trend-t{self.timeframe}_dc{self.donchian_entry}/{self.donchian_exit}"


@dataclass(frozen=True)
class TrendDecision:
    action: str  # enter / exit / hold / skip
    reason: TrendReason
    cct: int
    close: Decimal
    dch: Decimal | None = field(default=None)
    dcl: Decimal | None = field(default=None)
    entry: Decimal | None = field(default=None)
