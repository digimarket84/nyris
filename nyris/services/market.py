"""Logique marché (Binance read-only) : prix EUR par actif, batch, sync.

On-demand uniquement + petit cache mémoire TTL. EUR strict (paires directes).
Le sync met à jour binance_symbol/status mais NE modifie PAS is_tradeable.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from nyris.core.config import settings
from nyris.core.exceptions import ConflictError, NotFoundError
from nyris.models.asset import Asset
from nyris.services import binance

# Cache mémoire process : {binance_symbol: (price, deadline_monotonic)}
_CACHE: dict[str, tuple[Decimal, float]] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _cached_price(symbol: str) -> Decimal | None:
    hit = _CACHE.get(symbol)
    if hit is None:
        return None
    price, deadline = hit
    if time.monotonic() > deadline:
        _CACHE.pop(symbol, None)
        return None
    return price


def _store_price(symbol: str, price: Decimal) -> None:
    _CACHE[symbol] = (price, time.monotonic() + settings.market_cache_ttl)


def _get_asset(db: Session, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError(f"Asset id={asset_id} introuvable")
    return asset


def get_price_for_asset(db: Session, asset_id: int) -> dict:
    asset = _get_asset(db, asset_id)
    if not asset.binance_symbol:
        raise ConflictError(
            f"Aucune paire EUR Binance pour {asset.symbol} (prix indisponible)"
        )
    price = _cached_price(asset.binance_symbol)
    if price is None:
        price = binance.get_price(asset.binance_symbol)
        _store_price(asset.binance_symbol, price)
    return {
        "asset_id": asset.id,
        "symbol": asset.symbol,
        "binance_symbol": asset.binance_symbol,
        "price": price,
        "quote_currency": settings.binance_quote_currency,
        "as_of": datetime.now(UTC),
        "source": "binance",
    }


def get_all_prices(db: Session) -> dict:
    assets = list(
        db.scalars(
            select(Asset).where(Asset.binance_symbol.is_not(None)).order_by(Asset.symbol)
        )
    )
    remote = binance.get_all_prices()
    now = datetime.now(UTC)
    prices = []
    for asset in assets:
        price = remote.get(asset.binance_symbol)
        if price is None:
            continue
        _store_price(asset.binance_symbol, price)
        prices.append(
            {
                "asset_id": asset.id,
                "symbol": asset.symbol,
                "binance_symbol": asset.binance_symbol,
                "price": price,
                "quote_currency": settings.binance_quote_currency,
                "as_of": now,
                "source": "binance",
            }
        )
    return {
        "quote_currency": settings.binance_quote_currency,
        "count": len(prices),
        "as_of": now,
        "prices": prices,
    }


def sync_symbols(db: Session) -> dict:
    info = binance.get_exchange_info()
    quote = settings.binance_quote_currency
    now = datetime.now(UTC)
    assets = list(db.scalars(select(Asset).order_by(Asset.symbol)))

    tradable = not_listed = 0
    details = []
    for asset in assets:
        candidate = f"{asset.exchange_symbol}{quote}"
        entry = info.get(candidate)
        if entry and entry["quoteAsset"] == quote and entry["status"] == "TRADING":
            asset.binance_symbol = candidate
            asset.binance_status = "TRADING"
            tradable += 1
        else:
            asset.binance_symbol = None
            asset.binance_status = entry["status"] if entry else "NOT_LISTED"
            not_listed += 1
        asset.market_synced_at = now
        details.append(
            {
                "symbol": asset.symbol,
                "binance_symbol": asset.binance_symbol,
                "binance_status": asset.binance_status,
            }
        )

    db.commit()
    return {
        "checked": len(assets),
        "tradable": tradable,
        "not_listed": not_listed,
        "synced_at": now,
        "assets": details,
    }
