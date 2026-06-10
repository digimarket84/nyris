"""Couche adaptative = MONITEUR (alerte, pas auto-action). Le backtest a prouve qu'un kill-switch
auto DEGRADE l'edge mean-reversion (il coupe juste avant le rebond). Donc ici : surveillance
des stats glissantes par runner + alerte UNIQUEMENT sur degradation statistiquement significative.
La decision (vraie cassure de regime vs bruit) reste humaine. Lecture seule.

Usage : python -m scripts.edge_monitor  (ou PYTHONPATH=. python scripts/edge_monitor.py)
"""
import datetime as dt

from sqlalchemy import select

from nyris.core.database import SessionLocal
from nyris.models.pattern_trade import PatternTrade

ROLL = 30          # fenetre glissante
MIN_ROLL = 15      # en-dessous : echantillon insuffisant, pas d'alerte
PF_DEGRADED = 0.8  # < ce PF glissant (sur >=MIN_ROLL trades) = degradation reelle
PF_WATCH = 1.1
EPOCH_MR = dt.datetime(2026, 6, 10, tzinfo=dt.UTC)  # ere mistral long-only/compounding

# run_id -> (label, filtre side optionnel, epoch optionnel)
RUNS = [
    ("live-meanrev-v1", "MEANREV (edge valide)", None, None),
    ("live-mistral-v1", "MISTRAL long-only", "long", EPOCH_MR),
    ("live-trend-v1", "TREND (dormant)", None, None),
    ("live-pattern-v1", "pattern (pause)", None, None),
    ("live-perplexity-v1", "perplexity (temoin)", None, None),
    ("live-chatgpt-v1", "chatgpt (temoin)", None, None),
]


def pf(rets):
    gp = sum(x for x in rets if x > 0)
    gl = -sum(x for x in rets if x < 0)
    return gp / gl if gl else (999.0 if gp > 0 else 0.0)


def status(roll_rets):
    if len(roll_rets) < MIN_ROLL:
        return "DONNEES INSUFFISANTES", "info"
    p = pf(roll_rets)
    if p < PF_DEGRADED:
        return f"DEGRADE (PF glissant {p:.2f} < {PF_DEGRADED}) -> investiguer regime", "alert"
    if p < PF_WATCH:
        return f"SURVEILLANCE (PF glissant {p:.2f})", "watch"
    return f"OK (PF glissant {p:.2f})", "ok"


def main():
    db = SessionLocal()
    alerts = []
    print(f"=== MONITEUR D'EDGE (fenetre glissante {ROLL} trades) ===")
    for run_id, label, side, epoch in RUNS:
        q = select(PatternTrade.pnl_net).where(
            PatternTrade.run_id == run_id, PatternTrade.status == "closed",
            PatternTrade.pnl_net.is_not(None)).order_by(PatternTrade.closed_at)
        if side:
            q = q.where(PatternTrade.side == side)
        if epoch:
            q = q.where(PatternTrade.opened_at >= epoch)
        rets = [float(x) for x in db.scalars(q).all()]
        if not rets:
            print(f"  {label:<24} 0 trade")
            continue
        roll = rets[-ROLL:]
        st, lvl = status(roll)
        net_all = sum(rets)
        flag = {"alert": "[!]", "watch": "[~]", "ok": "[ok]", "info": "[..]"}[lvl]
        print(f"  {flag:<5}{label:<24} n={len(rets):<4} net={net_all:+7.2f}E  "
              f"PFtot={pf(rets):.2f}  | glissant: {st}")
        if lvl == "alert":
            alerts.append(f"{label}: {st}")
    print()
    if alerts:
        print("ALERTES (degradation statistiquement reelle -> decision humaine requise) :")
        for a in alerts:
            print("  ! " + a)
    else:
        print("Aucune degradation significative. (Rappel : ne PAS reagir au bruit / trades isoles.)")


if __name__ == "__main__":
    main()
