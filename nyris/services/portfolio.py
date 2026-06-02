"""Agrégation du portefeuille simulé (filtrable par période et par actif).

Sémantique validée :
- realized.* / by_asset / best/worst : trades `closed` dans la fenêtre [from, to)
  sur `closed_at` (+ filtre asset).
- open_exposure.* : snapshot COURANT des trades `open` (filtre asset seulement,
  jamais borné par from/to).
- draft & cancelled : exclus des montants.
- résultat vide => zéros / null (jamais d'erreur).
"""

from __future__ import annotations

from datetime import datetime
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


def build_summary(
    db: Session,
    from_: datetime | None = None,
    to: datetime | None = None,
    asset_id: int | None = None,
) -> dict:
    asset_cond = [SimulatedTrade.asset_id == asset_id] if asset_id is not None else []

    # Trades réalisés (closed) dans la fenêtre closed_at + filtre actif
    closed_cond = [*asset_cond, SimulatedTrade.status == TradeStatus.closed]
    if from_ is not None:
        closed_cond.append(SimulatedTrade.closed_at >= from_)
    if to is not None:
        closed_cond.append(SimulatedTrade.closed_at < to)

    closed_count, inv, exit_value, pnl = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(SimulatedTrade.amount_invested), 0),
            func.coalesce(func.sum(SimulatedTrade.exit_net_value), 0),
            func.coalesce(func.sum(SimulatedTrade.pnl_net), 0),
        ).where(*closed_cond)
    ).one()
    inv, exit_value, pnl = Decimal(inv), Decimal(exit_value), Decimal(pnl)
    realized = {
        "invested": round_money(inv),
        "exit_value": round_money(exit_value),
        "pnl_net": round_money(pnl),
        "pnl_percent": _pct(pnl, inv),
    }

    # Comptes par statut (filtre actif, état courant) ; closed = compte fenêtré
    counts = {status.value: 0 for status in TradeStatus}
    status_stmt = select(SimulatedTrade.status, func.count()).group_by(SimulatedTrade.status)
    if asset_cond:
        status_stmt = status_stmt.where(*asset_cond)
    for status, n in db.execute(status_stmt).all():
        counts[status.value] = int(n)
    counts["closed"] = int(closed_count)
    total = sum(counts.values())

    # Exposition ouverte : snapshot courant (filtre actif uniquement)
    open_cond = [*asset_cond, SimulatedTrade.status == TradeStatus.open]
    open_inv, open_n = db.execute(
        select(
            func.coalesce(func.sum(SimulatedTrade.amount_invested), 0),
            func.count(),
        ).where(*open_cond)
    ).one()
    open_exposure = {"invested": round_money(Decimal(open_inv)), "trades": int(open_n)}

    # Stats par actif (closed, fenêtre)
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
        .where(*closed_cond)
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
        "filters": {"from": from_, "to": to, "asset_id": asset_id, "date_field": "closed_at"},
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
