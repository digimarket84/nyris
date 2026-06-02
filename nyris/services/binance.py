"""Transport HTTP pur vers l'API publique Binance (market data, lecture seule).

Aucune clé API. Base URL configurable + fallback. Erreurs typées pour un
mapping HTTP propre côté route.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from nyris.core.config import settings


class BinanceError(Exception):
    """Erreur Binance de base."""


class BinanceUnavailable(BinanceError):
    """Réseau / timeout / 5xx / rate limit -> 503."""


class BinanceBadResponse(BinanceError):
    """Réponse 2xx mais contenu invalide/inattendu -> 502."""


class BinanceSymbolNotFound(BinanceError):
    """Symbole inconnu côté Binance -> 409."""


_PRICE_PATH = "/api/v3/ticker/price"
_EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"
_KLINES_PATH = "/api/v3/klines"


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.binance_timeout_connect,
        read=settings.binance_timeout_read,
        write=5.0,
        pool=5.0,
    )


def _bases() -> list[str]:
    bases = [settings.binance_base_url]
    if settings.binance_fallback_url and settings.binance_fallback_url not in bases:
        bases.append(settings.binance_fallback_url)
    return bases


def _get(path: str, params: dict | None = None) -> Any:
    """GET public avec bascule base -> fallback en cas d'indisponibilité."""
    last: BinanceError | None = None
    for base in _bases():
        try:
            with httpx.Client(base_url=base, timeout=_timeout()) as client:
                resp = client.get(path, params=params)
        except httpx.HTTPError as exc:
            last = BinanceUnavailable(f"Binance injoignable ({base}): {exc}")
            continue

        if resp.status_code in (418, 429):
            raise BinanceUnavailable("Binance rate limit / ban temporaire")
        if resp.status_code >= 500:
            last = BinanceUnavailable(f"Binance erreur serveur {resp.status_code} ({base})")
            continue
        if resp.status_code == 400:
            try:
                data = resp.json()
            except ValueError as exc:
                raise BinanceBadResponse("Réponse 400 illisible") from exc
            if isinstance(data, dict) and data.get("code") == -1121:
                raise BinanceSymbolNotFound(str(data.get("msg", "Invalid symbol")))
            raise BinanceBadResponse(f"Binance a refusé la requête: {data}")
        if resp.status_code != 200:
            last = BinanceUnavailable(f"Binance statut inattendu {resp.status_code}")
            continue

        try:
            return resp.json()
        except ValueError as exc:
            raise BinanceBadResponse(f"JSON Binance invalide: {exc}") from exc

    raise last or BinanceUnavailable("Binance injoignable")


def get_price(symbol: str) -> Decimal:
    data = _get(_PRICE_PATH, params={"symbol": symbol})
    if not isinstance(data, dict) or "price" not in data:
        raise BinanceBadResponse(f"Réponse prix inattendue: {data}")
    try:
        return Decimal(str(data["price"]))
    except (ArithmeticError, ValueError) as exc:
        raise BinanceBadResponse(f"Prix illisible: {data}") from exc


def get_all_prices() -> dict[str, Decimal]:
    data = _get(_PRICE_PATH)
    if not isinstance(data, list):
        raise BinanceBadResponse("Réponse /ticker/price inattendue")
    out: dict[str, Decimal] = {}
    for row in data:
        try:
            out[row["symbol"]] = Decimal(str(row["price"]))
        except (KeyError, ArithmeticError, ValueError):
            continue
    return out


def get_exchange_info() -> dict[str, dict]:
    """Retourne {symbol: {status, baseAsset, quoteAsset}} pour validation."""
    data = _get(_EXCHANGE_INFO_PATH)
    if not isinstance(data, dict) or "symbols" not in data:
        raise BinanceBadResponse("Réponse exchangeInfo inattendue")
    out: dict[str, dict] = {}
    for s in data["symbols"]:
        try:
            out[s["symbol"]] = {
                "status": s["status"],
                "baseAsset": s["baseAsset"],
                "quoteAsset": s["quoteAsset"],
            }
        except KeyError:
            continue
    return out


def get_klines(
    symbol: str,
    interval: str,
    limit: int = 1000,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[list]:
    """Bougies OHLCV (tableau de tableaux Binance). Public, sans clé."""
    params: dict = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time
    data = _get(_KLINES_PATH, params=params)
    if not isinstance(data, list):
        raise BinanceBadResponse("Réponse klines inattendue")
    return data
