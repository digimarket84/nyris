"""Runner générique des 4 stratégies LLM (oneshot, paper, bidirectionnel).

Une passe = pour chaque stratégie (perplexity/chatgpt/gemini/mistral) et chaque actif :
détecte un signal (llm_engines), ouvre/gère des trades dans `pattern_trades` (run_id dédié),
journalise dans strategy_decisions (idempotent). Sorties stop/TP au niveau exact assurées
par le pattern_monitor (1m). Le runner gère breakeven, reverse-on-opposite, partiel (Perplexity)
et time-exit. Isolé : ne touche jamais simulated_trades/short_trades ; baseline gelé.

Exécution : python -m nyris.strategy.llm_runner
"""

from __future__ import annotations

import fcntl
import logging
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nyris.models.asset import Asset
from nyris.models.pattern_trade import PatternTrade
from nyris.models.strategy_decision import StrategyDecision
from nyris.services import candles as candles_service
from nyris.services.binance import BinanceError
from nyris.strategy import pattern_pnl
from nyris.strategy.llm_engines import ENTRY_FNS, STRATEGIES
from nyris.strategy.llm_models import LlmStrategy
from nyris.strategy.recorder import evaluated_at_from_candle

logger = logging.getLogger("nyris.llm_runner")
LOCK_PATH = "/srv/nyris/llm-runner.lock"
_TF_HOURS = {"1m": 1 / 60, "5m": 5 / 60, "15m": 0.25, "1h": 1.0, "4h": 4.0}


class LlmRunnerBusy(Exception):
    pass


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise LlmRunnerBusy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _tf_hours(tf: str) -> float:
    return _TF_HOURS.get(tf, 0.25)


def _bump(s: dict, k: str) -> None:
    s[k] = s.get(k, 0) + 1


def _open_for_asset(db, asset_id, run_id):
    return list(db.scalars(select(PatternTrade).where(
        PatternTrade.asset_id == asset_id, PatternTrade.run_id == run_id,
        PatternTrade.status == "open")).all())


def _open_asset_count(db, run_id) -> int:
    return int(db.scalar(select(func.count(func.distinct(PatternTrade.asset_id))).where(
        PatternTrade.run_id == run_id, PatternTrade.status == "open")) or 0)


def _last_closed(db, asset_id, run_id):
    return db.scalar(select(PatternTrade).where(
        PatternTrade.asset_id == asset_id, PatternTrade.run_id == run_id,
        PatternTrade.status == "closed").order_by(PatternTrade.id.desc()))


def _decision_exists(db, asset_id, strat: LlmStrategy, cct: int) -> bool:
    return db.scalar(select(StrategyDecision.id).where(
        StrategyDecision.asset_id == asset_id, StrategyDecision.timeframe == strat.exec_tf,
        StrategyDecision.candle_close_time == cct,
        StrategyDecision.params_key == strat.params_key)) is not None


def _record(db, asset, strat, cct, close_price, action, reason, pstate, notes=None):
    db.add(StrategyDecision(
        evaluated_at=evaluated_at_from_candle(cct), asset_id=asset.id, symbol=asset.symbol,
        timeframe=strat.exec_tf, candle_close_time=cct, close_price=Decimal(str(close_price)),
        action=action, reason=reason, position_state=pstate, params_key=strat.params_key,
        run_id=strat.run_id, notes=notes))


def _build(asset, strat, side, entry, stop, tp, notional, reason, notes, cct):
    res = pattern_pnl.compute_entry(notional, Decimal(str(entry)), strat)
    return PatternTrade(
        asset_id=asset.id, status="open", side=side, pattern=strat.name,
        amount_invested=notional, entry_price=Decimal(str(entry)), quantity=res.quantity,
        stop_price=Decimal(str(stop)), take_profit_price=Decimal(str(tp)),
        commission_rate=strat.commission_rate, spread_rate=strat.spread_rate,
        slippage_rate=strat.slippage_rate, funding_rate_daily=strat.funding_rate_daily,
        entry_cost=res.entry_cost, entry_reason=reason, run_id=strat.run_id,
        params_key=strat.params_key, notes=notes, opened_at=evaluated_at_from_candle(cct))


def _close(db, trade, strat, exit_price, reason, cct):
    opened_ms = int(trade.opened_at.timestamp() * 1000)
    hours = max((cct - opened_ms) / 3_600_000, 0.0)
    res = pattern_pnl.compute_close(trade.side, trade.amount_invested, trade.quantity,
                                    trade.entry_cost, Decimal(str(exit_price)), strat, hours)
    trade.exit_price = Decimal(str(exit_price))
    trade.exit_cost = res.exit_cost
    trade.funding_cost = res.funding_cost
    trade.pnl_gross = res.pnl_gross
    trade.pnl_net = res.pnl_net
    trade.pnl_percent = res.pnl_percent
    trade.exit_reason = reason
    trade.status = "closed"
    trade.closed_at = evaluated_at_from_candle(cct)


def _r_orig(strat, t) -> float:
    return abs(float(t.take_profit_price) - float(t.entry_price)) / max(strat.reward_ratio, 0.01)


def _manage(db, strat, opens, cct, close):
    """Breakeven générique + BE partiel (Perplexity) + time-exit. Stop/TP gérés par le monitor."""
    tf_ms = _tf_hours(strat.exec_tf) * 3600 * 1000
    for t in opens:
        e = float(t.entry_price)
        # BE partiel Perplexity : jambe tp2 ouverte dont la jambe tp1 (même opened_at) est close
        if strat.partial and t.notes and "tp2" in t.notes:
            sib = db.scalar(select(PatternTrade).where(
                PatternTrade.run_id == strat.run_id, PatternTrade.asset_id == t.asset_id,
                PatternTrade.opened_at == t.opened_at, PatternTrade.notes.like("%tp1%")))
            if sib is not None and sib.status == "closed":
                be = e * (1.001 if t.side == "long" else 0.999)
                if (t.side == "long" and be > float(t.stop_price)) or \
                   (t.side == "short" and be < float(t.stop_price)):
                    t.stop_price = Decimal(str(be))
        # breakeven générique (R-based)
        elif strat.be_trigger_r > 0:
            R = _r_orig(strat, t)
            if t.side == "long" and close >= e + strat.be_trigger_r * R:
                be = e * (1 + strat.be_offset_pct)
                if be > float(t.stop_price):
                    t.stop_price = Decimal(str(be))
            elif t.side == "short" and close <= e - strat.be_trigger_r * R:
                be = e * (1 - strat.be_offset_pct)
                if be < float(t.stop_price):
                    t.stop_price = Decimal(str(be))
    # time-exit
    if strat.max_hold_bars > 0:
        for t in opens:
            if t.status != "open":
                continue
            bars = (cct - int(t.opened_at.timestamp() * 1000)) / tf_ms
            if bars < strat.max_hold_bars:
                continue
            if strat.partial:
                # ne sortir au temps que si la jambe TP1 est encore ouverte
                tp1_open = any(("tp1" in (x.notes or "")) and x.status == "open" for x in opens)
                if not tp1_open:
                    continue
            _close(db, t, strat, close, "exit_time", cct)


def _open_signal(db, asset, strat, sig, cct, summary):
    full = (strat.starting_capital * strat.position_fraction).quantize(Decimal("0.01"))
    if strat.partial and sig.tp2 is not None:
        half = (full / 2).quantize(Decimal("0.01"))
        db.add(_build(asset, strat, sig.side, sig.entry, sig.stop, sig.tp, half,
                      sig.reason, f"llm:{strat.name}:tp1", cct))
        db.add(_build(asset, strat, sig.side, sig.entry, sig.stop, sig.tp2, half,
                      sig.reason, f"llm:{strat.name}:tp2", cct))
    else:
        db.add(_build(asset, strat, sig.side, sig.entry, sig.stop, sig.tp, full,
                      sig.reason, f"llm:{strat.name}", cct))
    _bump(summary, "enter_" + sig.side)


def process_asset(db, asset, strat, exec_candles, ctx_candles, summary):
    cct = exec_candles[-1].close_time
    if _decision_exists(db, asset.id, strat, cct):
        _bump(summary, "already_processed")
        return
    close = float(exec_candles[-1].close)
    opens = _open_for_asset(db, asset.id, strat.run_id)
    sig = ENTRY_FNS[strat.name](exec_candles, ctx_candles)

    if opens:
        side = opens[0].side
        if strat.reverse_on_opposite and sig is not None and sig.side != side:
            for t in opens:
                _close(db, t, strat, close, "exit_reverse", cct)
            opens = []  # devient flat -> on enchaîne sur l'ouverture inverse
        else:
            _manage(db, strat, opens, cct, close)
            _record(db, asset, strat, cct, close, "hold", "hold_in_position", "open")
            db.commit()
            _bump(summary, "hold_in_position")
            return

    if sig is not None:
        if _open_asset_count(db, strat.run_id) >= strat.max_open_positions:
            _record(db, asset, strat, cct, close, "skip", "skip_blocked_max_positions", "flat")
            db.commit()
            _bump(summary, "skip_blocked_max_positions")
            return
        if strat.cooldown_bars > 0:
            last = _last_closed(db, asset.id, strat.run_id)
            bad = last is not None and last.pnl_net is not None and last.pnl_net < 0
            if bad and last.closed_at:
                tf_ms = _tf_hours(strat.exec_tf) * 3600 * 1000
                if (cct - int(last.closed_at.timestamp() * 1000)) / tf_ms < strat.cooldown_bars:
                    _record(db, asset, strat, cct, close, "skip", "skip_blocked_cooldown", "flat")
                    db.commit()
                    _bump(summary, "skip_blocked_cooldown")
                    return
        _open_signal(db, asset, strat, sig, cct, summary)
        _record(db, asset, strat, cct, close, "enter", sig.reason, "flat")
        db.commit()
    else:
        _record(db, asset, strat, cct, close, "hold", "hold_no_signal", "flat")
        db.commit()
        _bump(summary, "hold_no_signal")


ENTRY_UNIVERSE = (
    "BTC", "ETH", "SOL", "NEAR", "SUI", "LINK", "AVAX", "DOGE", "PEPE",
    "POND", "BABY", "HOME", "LA",
)


def run_cycle(db: Session) -> dict:
    summary: dict = {"runner": "llm"}
    cache: dict = {}

    def get(bsym, tf, limit):
        k = (bsym, tf)
        if k not in cache:
            cache[k] = candles_service.get_candles(bsym, tf, limit)
        return cache[k]

    assets = {a.symbol: a for a in db.scalars(select(Asset).where(Asset.is_tradeable.is_(True)))}
    for strat in STRATEGIES:
        st_sum: dict = {}
        for sym in ENTRY_UNIVERSE:
            asset = assets.get(sym)
            if asset is None or not asset.binance_symbol:
                continue
            try:
                ex = get(asset.binance_symbol, strat.exec_tf, strat.exec_limit)
                cx = get(asset.binance_symbol, strat.ctx_tf, strat.ctx_limit)
            except BinanceError:
                _bump(st_sum, "data_error")
                continue
            if len(ex) < 30 or len(cx) < 30:
                _bump(st_sum, "fail_safe")
                continue
            try:
                process_asset(db, asset, strat, ex, cx, st_sum)
            except Exception:
                db.rollback()
                logger.exception("erreur llm %s/%s", strat.name, sym)
                _bump(st_sum, "errors")
        summary[strat.name] = st_sum
    return summary


def _main() -> None:
    import json

    from nyris.core.database import SessionLocal
    from nyris.core.logging import configure_logging

    configure_logging()
    try:
        with cycle_lock():
            with SessionLocal() as db:
                summary = run_cycle(db)
            logger.info("cycle llm terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except LlmRunnerBusy:
        logger.warning("un autre cycle llm est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
