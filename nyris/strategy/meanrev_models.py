"""Config + types du runner MEAN-REVERSION daily (long-only, RSI survendu).

Edge validé (round 1-5, 7 ans + IS/OOS + plateau + sensibilité coûts) : sur le
marché actuel (choppy/range), acheter les creux survendus des ALTS volatils et
revendre le rebond bat tout le reste. OOS positif (PF 1.65). Majors EXCLUS
(BTC/ETH/SOL : peu volatils -> mean-reversion négative). Long spot -> funding 0.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal


class MeanRevReason(enum.StrEnum):
    skip_no_data = "skip_no_data"
    hold_flat = "hold_flat"  # hors marché : pas (encore) de survente
    hold_in_position = "hold_in_position"
    enter_oversold = "enter_oversold"  # RSI < seuil -> achat du creux
    exit_recovered = "exit_recovered"  # rebond : close > SMA de sortie
    exit_max_hold = "exit_max_hold"    # durée max atteinte (anti bag-holding)


@dataclass(frozen=True)
class MeanRevParams:
    # Univers : alts volatils uniquement (majors retirés, négatifs en backtest).
    universe: tuple[str, ...] = (
        "LINK", "AVAX", "NEAR", "DOGE", "SUI", "PEPE", "ENA",
        "WLD", "ZEC", "POND", "BABY", "HOME", "LA",
    )
    timeframe: str = "1d"
    rsi_period: int = 14
    rsi_buy: float = 35.0      # achat si RSI(14) < 35 (survendu modéré)
    exit_sma: int = 10         # sortie si close > SMA(10) (rebond confirmé)
    max_hold_days: int = 20    # sortie forcée après 20 jours
    per_position: Decimal = Decimal("100")  # notional € par actif (paper)
    commission_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    funding_rate_daily: Decimal = Decimal("0")  # long spot -> pas de portage
    run_id: str = "live-meanrev-v1"
    allow_entries: bool = True  # False = mode extinction : plus de nouvelles entrees, sorties OK

    def key(self) -> str:
        return (
            f"meanrev-t{self.timeframe}_rsi{self.rsi_period}"
            f"<{int(self.rsi_buy)}_sma{self.exit_sma}_h{self.max_hold_days}"
        )


@dataclass(frozen=True)
class MeanRevDecision:
    action: str  # enter / exit / hold / skip
    reason: MeanRevReason
    cct: int
    close: Decimal
    rsi: Decimal | None = field(default=None)
    sma: Decimal | None = field(default=None)
    entry: Decimal | None = field(default=None)
