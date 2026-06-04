"""Config et taxonomie du runner SHORT (indépendant du baseline).

V2 : exécution multi-timeframe.
  - filtre de tendance/contexte sur un timeframe supérieur (`context_timeframe`),
  - signal d'entrée + exécution sur `timeframe` (1m).
Le baseline n'est NI importé NI modifié.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal


class ShortReason(enum.StrEnum):
    skip_no_data = "skip_no_data"
    hold_no_downtrend = "hold_no_downtrend"  # contexte non baissier
    hold_no_setup = "hold_no_setup"  # baissier mais pas de rejet 1m
    hold_in_position = "hold_in_position"
    enter_short_signal = "enter_short_signal"
    exit_short_stop = "exit_short_stop"
    exit_short_take_profit = "exit_short_take_profit"
    exit_short_reclaim = "exit_short_reclaim"  # prix reprend l'EMA fadée = mvt cassé
    exit_short_trend_recovered = "exit_short_trend_recovered"
    exit_short_time = "exit_short_time"  # conservé (taxonomie) mais plus émis
    skip_blocked_max_positions = "skip_blocked_max_positions"
    skip_blocked_exposure = "skip_blocked_exposure"
    skip_blocked_cooldown = "skip_blocked_cooldown"
    skip_blocked_min_notional = "skip_blocked_min_notional"
    skip_blocked_volatility = "skip_blocked_volatility"  # ATR%/bougie hors bande


@dataclass(frozen=True)
class ShortParams:
    # Univers (short uniquement ; le baseline garde son UNIVERSE figé BTC/ETH/SOL).
    # Extension : majors + paires plus volatiles disponibles sur Binance EUR.
    # INJ exclu (pas de paire INJEUR sur le flux). LINK/AVAX/PEPE sont fins :
    # protegés par le plancher de volatilite min_atr_pct (n'entre que si ca bouge).
    universe: tuple[str, ...] = (
        "BTC", "ETH", "SOL", "NEAR", "SUI", "LINK", "AVAX", "DOGE", "PEPE",
    )
    # Timeframes : exécution sur 5m (mouvements assez amples vs frais), contexte 1h
    timeframe: str = "5m"  # signal d'entrée + exécution
    context_timeframe: str = "1h"  # filtre de tendance supérieur
    context_ema: int = 50  # contexte baissier si close_1h < EMA(context_ema)_1h
    # Indicateurs d'exécution (sur `timeframe`)
    ema_pullback: int = 20  # EMA 1m de référence du rejet
    atr_period: int = 14
    ema_trend: int = 200  # conservé pour le mode legacy/snapshot (non utilisé en MTF)
    # Sorties (profil agressif : cible lointaine pour dépasser les frais)
    atr_stop_mult: float = 1.5
    reward_r: float = 2.5
    max_hold: int = 60  # 60 bougies 5m = 5 h max en position
    max_stop_pct: float = 0.02  # le stop ne peut être plus loin que 2 % (1m)
    cooldown: int = 3  # 3 bougies 1m = 3 min entre deux trades d'un même actif
    # Garde-fou volatilité (proxy "vol/spread anormaux") : bande sur ATR/close par bougie.
    # Plancher renforcé (0.03 % -> 0.08 %) pour ne PAS trader les bougies trop plates
    # des paires fines (LINK/AVAX/PEPE) où le spread réel dominerait -> exécution "sale".
    min_atr_pct: float = 0.0008  # 0.08 % : sous ce seuil, on s'abstient (anti-bruit/dirty)
    max_atr_pct: float = 0.012  # 1.2 % : au-dessus, volatilité anormale -> on s'abstient
    # Sizing (capital de référence 50 €, notional fixe non-compounding)
    starting_capital: Decimal = Decimal("50")
    position_fraction: Decimal = Decimal("0.5")  # 25 € par short
    max_open_positions: int = 3  # jusqu'à 3 shorts en parallèle (évite la famine des paires)
    max_total_exposure: Decimal = Decimal("1.5")  # cap 50€*1.5 = 75€ -> 3 x 25€ tiennent
    min_notional: Decimal = Decimal("10")
    # Coûts (par côté sauf funding qui est /jour)
    commission_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    funding_rate_daily: Decimal = Decimal("0.0003")
    # Identité (run_id court <= 40 caractères) ; v3 = régime 5m agressif
    run_id: str = "live-short-v3"

    def key(self) -> str:
        # clé <= 80 caractères, distincte du baseline ET de la V1 short
        return (
            f"short-x{self.context_timeframe}{self.context_ema}"
            f"-t{self.timeframe}_p{self.ema_pullback}"
            f"_sl{self.atr_stop_mult}_R{self.reward_r}_h{self.max_hold}"
        )
