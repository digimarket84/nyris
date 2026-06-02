"""Service de bougies : récupère les klines Binance et les mappe en Candle."""

from __future__ import annotations

from nyris.services import binance
from nyris.strategy.models import Candle


def get_candles(binance_symbol: str, interval: str = "4h", limit: int = 1000) -> list[Candle]:
    rows = binance.get_klines(binance_symbol, interval, limit)
    # On exclut la dernière bougie si elle est potentiellement en cours :
    # déterminisme = on ne travaille que sur des bougies clôturées. Binance
    # renvoie la bougie courante en dernier ; on la retire par sécurité.
    candles = [Candle.from_binance(r) for r in rows]
    return candles[:-1] if candles else candles
