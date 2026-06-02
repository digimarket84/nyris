"""Agrégation du portefeuille simulé.

Stratégie : agrégation côté base (count/sum), pourcentages et arrondis calculés
en Python avec Decimal (jamais en SQL). Le PnL réalisé ne compte que les trades
fermés ; les trades ouverts sont isolés dans `open_exposure` ; les annulés sont
exclus de tous les montants.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.simulated_trade import SimulatedTrade, TradeStatus
from nyris.services.pnl import round_money, round_pct


def _pct(pnl_net: Decimal, invested: Decimal) -> Decimal | None:
    if invested == 0:
        return None
    return round_pct(pnl_net / invested * Decimal(100))


def build_summary(db: Session) -> dict:
    # --- Comptes par statut ---
    counts = {status.value: 0 for status in TradeStatus}
    for status, n in db.execute(
        select(SimulatedTrade.status, func.count()).group_by(SimulatedTrade.status)
    ).all():
        counts[status.value] = int(n)
    total = sum(counts.values())

    # --- Réalisé (trades fermés) ---
    inv, exit_value, pnl = db.execute(
        select(
            func.coalesce(func.sum(SimulatedTrade.amount_invested), 0),
            func.coalesce(func.sum(SimulatedTrade.exit_net_value), 0),
            func.coalesce(func.sum(SimulatedTrade.pnl_net), 0),
        ).where(SimulatedTrade.status == TradeStatus.closed)
    ).one()
    inv, exit_value, pnl = Decimal(inv), Decimal(exit_value), Decimal(pnl)
    realized = {
        "invested": round_money(inv),
        "exit_value": round_money(exit_value),
        "pnl_net": round_money(pnl),
        "pnl_percent": _pct(pnl, inv),
    }

    # --- Exposition ouverte (trades ouverts) ---
    open_inv, open_count = db.execute(
        select(
            func.coalesce(func.sum(SimulatedTrade.amount_invested), 0),
            func.count(),
        ).where(SimulatedTrade.status == TradeStatus.open)
    ).one()
    open_exposure = {"invested": round_money(Decimal(open_inv)), "trades": int(open_count)}

    # --- Stats par actif (trades fermés) ---
    by_asset: list[dict] = []
    rows = db.execute(
        select(
            Asset.id,
            Asset.symbol,
            Asset.display_name,
            func.count(),
            func.coalesce(func.sum(SimulatedTrade.amount_invested), 0),
            func.coalesce(func.sum(SimulatedTrade.exit_net_value), 0),
            func.coalesce(func.sum(SimulatedTrade.pnl_net), 0),
        )
        .join(SimulatedTrade, SimulatedTrade.asset_id == Asset.id)
        .where(SimulatedTrade.status == TradeStatus.closed)
        .group_by(Asset.id, Asset.symbol, Asset.display_name)
        .order_by(Asset.symbol)
    ).all()
    for aid, symbol, display_name, cnt, a_inv, a_exit, a_pnl in rows:
        a_inv, a_exit, a_pnl = Decimal(a_inv), Decimal(a_exit), Decimal(a_pnl)
        by_asset.append(
            {
                "asset_id": aid,
                "symbol": symbol,
                "display_name": display_name,
                "closed_trades": int(cnt),
                "invested": round_money(a_inv),
                "exit_value": round_money(a_exit),
                "pnl_net": round_money(a_pnl),
                "pnl_percent": _pct(a_pnl, a_inv),
            }
        )

    # --- Meilleur / pire actif (par PnL net €) ---
    best_asset = worst_asset = None
    if by_asset:
        best = max(by_asset, key=lambda x: x["pnl_net"])
        worst = min(by_asset, key=lambda x: x["pnl_net"])
        best_asset = {
            "symbol": best["symbol"],
            "pnl_net": best["pnl_net"],
            "pnl_percent": best["pnl_percent"],
        }
        worst_asset = {
            "symbol": worst["symbol"],
            "pnl_net": worst["pnl_net"],
            "pnl_percent": worst["pnl_percent"],
        }

    return {
        "currency": "EUR",
        "counts": {
            "total": total,
            "draft": counts["draft"],
            "open": counts["open"],
            "closed": counts["closed"],
            "cancelled": counts["cancelled"],
        },
        "realized": realized,
        "open_exposure": open_exposure,
        "by_asset": by_asset,
        "best_asset": best_asset,
        "worst_asset": worst_asset,
    }
