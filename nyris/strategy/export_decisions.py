"""Export backtest -> strategy_decisions.

Rejoue l'historique bougie par bougie, reproduit le cycle de position (pour des
décisions de sortie correctes) et journalise CHAQUE évaluation via le recorder.
Idempotent (contrainte d'unicité), regroupé par `run_id`.

- Aucune modification du moteur pur (utilise `_decide` sur indicateurs précalculés).
- Aucun trade réel/simulé créé : `simulated_trade_id` reste null.
- Pas de cooldown ici : on journalise les décisions PURES de `evaluate`.

Exécution : python -m nyris.strategy.export_decisions [run_id]
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.strategy_decision import StrategyDecision
from nyris.strategy.engine import _decide, compute_indicators, warmup
from nyris.strategy.models import Action, Candle, PositionState, StrategyParams
from nyris.strategy.recorder import build_decision_record

# Config candidate V1.1 (priorité)
V1_1 = StrategyParams(timeframe="4h", atr_stop_mult=1.5, reward_r=1.5)
ASSETS = ["BTC", "ETH", "SOL"]
TARGET_CANDLES = 6600


def export_asset(
    db: Session, asset: Asset, candles: list[Candle], params: StrategyParams, run_id: str
) -> dict:
    """Journalise toutes les évaluations d'un actif. Retourne un résumé."""
    warm = warmup(params)
    summary = {
        "symbol": asset.symbol,
        "n_candles": len(candles),
        "evaluated": 0,
        "inserted": 0,
        "skipped": 0,
        "actions": {},
        "reasons": {},
    }
    if len(candles) <= warm + 1:
        return summary

    ef, es, et, at = compute_indicators(candles, params)
    existing = set(
        db.scalars(
            select(StrategyDecision.candle_close_time).where(
                StrategyDecision.asset_id == asset.id,
                StrategyDecision.timeframe == params.timeframe,
                StrategyDecision.params_key == params.key(),
            )
        ).all()
    )

    actions: Counter = Counter()
    reasons: Counter = Counter()
    position: dict | None = None
    entry_index: int | None = None
    new_rows = []

    for i in range(warm, len(candles)):
        pos_state = None
        if position is not None:
            pos_state = PositionState(
                position["entry"], position["stop"], position["tp"], i - entry_index
            )
        dec = _decide(i, ef, es, et, at, candles, pos_state, params)
        pstate = "open" if position is not None else "flat"

        actions[dec.action.value] += 1
        reasons[dec.reason.value] += 1
        summary["evaluated"] += 1

        cct = candles[i].close_time
        if cct in existing:
            summary["skipped"] += 1
        else:
            new_rows.append(build_decision_record(asset, params, dec, pstate, run_id=run_id))
            existing.add(cct)
            summary["inserted"] += 1

        # avance la position "papier" en mémoire (rien n'est persisté comme trade)
        if position is None and dec.action == Action.enter:
            position = {"entry": dec.entry, "stop": dec.stop, "tp": dec.take_profit}
            entry_index = i
        elif position is not None and dec.action == Action.exit:
            position = None
            entry_index = None

    if new_rows:
        db.add_all(new_rows)
        db.commit()

    summary["actions"] = dict(actions)
    summary["reasons"] = dict(reasons)
    return summary


def _main() -> None:
    import json
    import sys

    from nyris.core.database import SessionLocal
    from nyris.services import candles as candles_service

    params = V1_1
    run_id = sys.argv[1] if len(sys.argv) > 1 else f"export-{params.key()}"

    tot_actions: Counter = Counter()
    tot_reasons: Counter = Counter()
    tot_inserted = tot_skipped = 0
    print(f"run_id = {run_id}")
    print(f"config = {params.key()}\n")

    with SessionLocal() as db:
        for sym in ASSETS:
            asset = db.scalar(select(Asset).where(Asset.symbol == sym))
            if asset is None:
                print(f"{sym}: actif introuvable, ignoré")
                continue
            candles = candles_service.get_candles_paginated(
                f"{sym}EUR", params.timeframe, TARGET_CANDLES
            )
            res = export_asset(db, asset, candles, params, run_id)
            tot_actions.update(res["actions"])
            tot_reasons.update(res["reasons"])
            tot_inserted += res["inserted"]
            tot_skipped += res["skipped"]
            print(
                f"{sym}: {res['n_candles']} bougies | évaluées={res['evaluated']} "
                f"insérées={res['inserted']} ignorées={res['skipped']}"
            )

    print("\n=== Agrégé ===")
    print(f"insérées={tot_inserted}  ignorées(idempotence)={tot_skipped}")
    print(f"actions  = {dict(tot_actions)}")
    print(f"reasons  = {json.dumps(dict(tot_reasons), ensure_ascii=False)}")


if __name__ == "__main__":
    _main()
