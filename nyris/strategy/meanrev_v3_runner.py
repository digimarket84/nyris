"""Runner MEANREV V3 — 4 simulations paper en parallele, compte 50E chacune, COMPOUNDING.

Meme moteur que v1/v2 (RSI14<35 long, exit close>SMA10 ou cap 20j) mais SIZING capital-realiste :
- chaque sim a K slots ; mise = equity/K (compounding : grossit avec l'equity, equity=50+realise) ;
- contrainte de capacite : si slots pleins ou cash epuise, on RATE le signal ;
- selection : quand on ne peut pas tout prendre, on prend les PLUS SURVENDUS (RSI le plus bas).
Univers = v2 sans majors. Meme flux de signaux pour les 4 sims, seul le sizing differe.
Isole ; baseline + v1/v2 intacts. Garde-fou bougie perimee inclus.

Exécution : python -m nyris.strategy.meanrev_v3_runner
"""

from __future__ import annotations

import fcntl
import json
import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.core.database import SessionLocal
from nyris.core.logging import configure_logging
from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import pattern_pnl
from nyris.strategy.indicators import rsi as rsi_ind
from nyris.strategy.indicators import sma as sma_ind
from nyris.strategy.meanrev_v3_universe import PAIRS
from nyris.strategy.recorder import evaluated_at_from_candle

logger = logging.getLogger("nyris.meanrev_v3_runner")
LOCK_PATH = "/srv/nyris/meanrev-v3-runner.lock"
CANDLE_LIMIT = 200
DAY_MS = 86_400_000
STALE_MS = 3 * DAY_MS
RSI_PERIOD = 14
RSI_BUY = 35.0
EXIT_SMA = 10
MAX_HOLD = 20
START = 50.0
MIN_NOTIONAL = 1.0  # en-dessous on n'ouvre pas (capital epuise)

COMM = Decimal("0.001")
SPREAD = Decimal("0.0005")
SLIP = Decimal("0.0005")
FUND = Decimal("0")

# (run_id, K slots) — mise initiale = 50/K = 1/2/5/10 EUR
SIMS = [
    ("live-meanrev-v3-1e", 50),
    ("live-meanrev-v3-2e", 25),
    ("live-meanrev-v3-5e", 10),
    ("live-meanrev-v3-10e", 5),
]


class _Costs:
    commission_rate = COMM
    spread_rate = SPREAD
    slippage_rate = SLIP
    funding_rate_daily = FUND


PARAMS = _Costs()


class MeanRevV3Busy(Exception):
    pass


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise MeanRevV3Busy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _bump(s, k):
    s[k] = s.get(k, 0) + 1


def _build(asset, run_id, notional: Decimal, entry_price: Decimal, cct):
    res = pattern_pnl.compute_entry(notional, entry_price, PARAMS)
    return PatternTrade(
        asset_id=asset.id, status="open", side="long", pattern="meanrev",
        amount_invested=notional, entry_price=entry_price, quantity=res.quantity,
        stop_price=None, take_profit_price=None,
        commission_rate=COMM, spread_rate=SPREAD, slippage_rate=SLIP, funding_rate_daily=FUND,
        entry_cost=res.entry_cost, entry_reason="enter_oversold", run_id=run_id,
        params_key=run_id, notes="auto:meanrev-v3", opened_at=evaluated_at_from_candle(cct))


def _close(trade, exit_price: Decimal, reason, cct):
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    hours = max((cct - opened_ms) / 3_600_000, 0.0)
    res = pattern_pnl.compute_close("long", trade.amount_invested, trade.quantity,
                                    trade.entry_cost, exit_price, PARAMS, hours)
    trade.exit_price = exit_price
    trade.exit_cost = res.exit_cost
    trade.funding_cost = res.funding_cost
    trade.pnl_gross = res.pnl_gross
    trade.pnl_net = res.pnl_net
    trade.pnl_percent = res.pnl_percent
    trade.exit_reason = reason
    trade.status = "closed"
    trade.closed_at = evaluated_at_from_candle(cct)


def _market_data(db: Session) -> dict:
    """Calcule UNE fois par cycle les signaux par actif (partages par les 4 sims)."""
    data: dict = {}
    warm = max(RSI_PERIOD + 1, EXIT_SMA) + 2
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    for sym in PAIRS:
        asset = db.scalar(select(Asset).where(Asset.symbol == sym))
        if asset is None or not asset.is_tradeable or not asset.binance_symbol:
            continue
        try:
            cands = candles_service.get_candles(asset.binance_symbol, "1d", CANDLE_LIMIT)
        except BinanceError:
            continue
        if len(cands) < warm:
            continue
        cct = cands[-1].close_time
        if now_ms - cct > STALE_MS:  # garde-fou bougie perimee
            continue
        closes = [float(c.close) for c in cands]
        r = rsi_ind(closes, RSI_PERIOD)[-1]
        s = sma_ind(closes, EXIT_SMA)[-1]
        if r is None or s is None:
            continue
        data[asset.id] = {
            "asset": asset, "cct": cct, "close_f": closes[-1],
            "close": Decimal(str(closes[-1])), "rsi": r, "sma": s,
        }
    return data


def process_sim(db: Session, run_id: str, k: int, data: dict, summary: dict) -> None:
    opens = list(db.scalars(select(PatternTrade).where(
        PatternTrade.run_id == run_id, PatternTrade.status == "open")).all())
    # --- SORTIES ---
    for t in opens:
        d = data.get(t.asset_id)
        if d is None:  # pas de donnee fraiche -> on garde (le garde-fou empeche les nouvelles)
            continue
        bars = max(int((d["cct"] - int(t.opened_at.timestamp() * 1000)) / DAY_MS), 0)
        if bars >= MAX_HOLD:
            _close(t, d["close"], "exit_max_hold", d["cct"])
            _bump(summary, f"{run_id}:exit")
        elif d["close_f"] > d["sma"]:
            _close(t, d["close"], "exit_recovered", d["cct"])
            _bump(summary, f"{run_id}:exit")
    db.flush()
    # --- CAPITAL (equity = 50 + realise ; cash = equity - investi ouvert) ---
    realized = float(db.scalar(select(func.coalesce(func.sum(PatternTrade.pnl_net), 0)).where(
        PatternTrade.run_id == run_id, PatternTrade.status == "closed")) or 0)
    equity = START + realized
    open_after = list(db.scalars(select(PatternTrade).where(
        PatternTrade.run_id == run_id, PatternTrade.status == "open")).all())
    held = {t.asset_id for t in open_after}
    cash = equity - sum(float(t.amount_invested) for t in open_after)
    slots_free = k - len(open_after)
    size = equity / k
    # --- ENTREES : survendus non detenus, des PLUS survendus en premier ---
    cands = [d for aid, d in data.items() if d["rsi"] < RSI_BUY and aid not in held]
    cands.sort(key=lambda d: d["rsi"])
    for d in cands:
        if slots_free <= 0:
            break
        invest = min(size, cash)
        if invest < MIN_NOTIONAL:
            break
        db.add(_build(d["asset"], run_id, Decimal(str(round(invest, 2))), d["close"], d["cct"]))
        cash -= invest
        slots_free -= 1
        _bump(summary, f"{run_id}:enter")
    db.commit()
    summary[f"{run_id}:equity"] = round(equity, 2)
    summary[f"{run_id}:open"] = k - slots_free


def run_cycle(db: Session) -> dict:
    summary: dict = {"runner": "meanrev-v3"}
    data = _market_data(db)
    summary["assets_ok"] = len(data)
    for run_id, k in SIMS:
        try:
            process_sim(db, run_id, k, data, summary)
        except Exception:
            db.rollback()
            logger.exception("erreur meanrev-v3 sim %s", run_id)
            _bump(summary, "errors")
    return summary


def _main() -> None:
    configure_logging()
    try:
        with cycle_lock():
            with SessionLocal() as db:
                summary = run_cycle(db)
            logger.info("cycle meanrev-v3 terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except MeanRevV3Busy:
        logger.warning("un autre cycle meanrev-v3 est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
