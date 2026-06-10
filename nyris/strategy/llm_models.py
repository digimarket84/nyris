"""Config commune des runners LLM (bidirectionnels). Stockage dans pattern_trades.

Chaque stratégie = une fonction d'entrée propre (llm_engines) + une config runner-level
ici (timeframes, breakeven, reverse, partial, sizing). Les sorties stop/TP sont gérées
au niveau exact par le pattern_monitor (1m) ; le breakeven/reverse/time-exit par le runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LlmSignal:
    side: str  # long / short
    entry: float
    stop: float
    tp: float
    reason: str
    tp2: float | None = None  # 2e palier (Perplexity, partiel 50/50)


@dataclass(frozen=True)
class LlmStrategy:
    name: str
    run_id: str
    exec_tf: str
    ctx_tf: str
    exec_limit: int
    ctx_limit: int
    reward_ratio: float = 2.0  # |tp-entry| = reward_ratio * R  (sert à retrouver R pour le BE)
    be_trigger_r: float = 0.0  # breakeven à X*R de profit (0 = désactivé / géré à part)
    be_offset_pct: float = 0.0  # stop ramené à entry*(1 ± offset)
    reverse_on_opposite: bool = False
    partial: bool = False  # Perplexity : sortie 50% TP1 + 50% TP2
    max_hold_bars: int = 0  # time-exit (0 = aucun)
    cooldown_bars: int = 0  # après une sortie perdante
    starting_capital: Decimal = Decimal("50")
    position_fraction: Decimal = Decimal("0.5")  # 25 € / signal (réparti si partiel)
    max_open_positions: int = 2
    commission_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    funding_rate_daily: Decimal = Decimal("0.0003")
    long_only: bool = False  # ignore les signaux short (ex. mistral)
    compound: bool = False  # mise = capital*fraction, capital qui grossit/rétrécit du PnL réalisé
    compound_epoch_ms: int = 0  # début de l'ère compounding (PnL compté à partir de là)

    @property
    def params_key(self) -> str:
        return self.run_id
