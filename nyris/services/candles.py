"""Service de bougies : récupère les klines Binance et les mappe en Candle."""

from __future__ import annotations

from nyris.services import binance
from nyris.strategy.models import Candle


def get_candles(binance_symbol: str, interval: str = "4h", limit: int = 1000) -> list[Candle]:
    """Une seule requête (max 1000). Exclut la dernière bougie (possiblement en cours)."""
    rows = binance.get_klines(binance_symbol, interval, limit)
    candles = [Candle.from_binance(r) for r in rows]
    return candles[:-1] if candles else candles


def get_candles_paginated(
    binance_symbol: str, interval: str = "4h", target: int = 6600
) -> list[Candle]:
    """Récupère un historique long (> 1000) par pagination arrière (endTime).

    Déterministe à données fixées : on remonte le temps via endTime sans dépendre
    de l'heure système. Exclut la dernière bougie (possiblement en cours).
    """
    rows: list[list] = []
    end_time: int | None = None
    while len(rows) < target:
        batch = binance.get_klines(binance_symbol, interval, limit=1000, end_time=end_time)
        if not batch:
            break
        rows = batch + rows  # on préfixe le lot plus ancien
        oldest_open = int(batch[0][0])
        end_time = oldest_open - 1
        if len(batch) < 1000:
            break  # plus d'historique disponible
    rows = rows[-target:]
    candles = [Candle.from_binance(r) for r in rows]
    return candles[:-1] if candles else candles
