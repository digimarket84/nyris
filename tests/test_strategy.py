"""Tests du moteur de décision pur evaluate()."""

from decimal import Decimal

from nyris.strategy.engine import evaluate
from nyris.strategy.indicators import ema
from nyris.strategy.models import Action, Candle, PositionState, Reason, StrategyParams

# Paramètres réduits pour des séries courtes (la logique est identique)
P = StrategyParams(
    ema_fast=2, ema_slow=3, ema_trend=5, atr_period=3,
    atr_stop_mult=2.0, reward_r=2.0, max_hold=5, max_stop_pct=0.9,
)
_STEP = 4 * 3600 * 1000


def mk(closes, hi=None, lo=None):
    out = []
    for idx, c in enumerate(closes):
        cd = Decimal(str(c))
        out.append(
            Candle(
                open_time=idx * _STEP,
                close_time=(idx + 1) * _STEP,
                open=cd,
                high=Decimal(str(hi[idx])) if hi else cd,
                low=Decimal(str(lo[idx])) if lo else cd,
                close=cd,
                volume=Decimal("1"),
            )
        )
    return out


def test_no_data():
    d = evaluate(mk([100, 101, 102]), None, P)
    assert d.action == Action.skip and d.reason == Reason.no_data


def test_downtrend_pas_dentree():
    closes = [120, 118, 116, 114, 112, 110, 108, 106, 104, 102]
    d = evaluate(mk(closes), None, P)
    assert d.action == Action.hold and d.reason == Reason.flat_no_trend


def test_entree_sur_croisement_en_tendance():
    closes = [100, 100, 100, 100, 100, 99, 98, 101, 106, 112, 119, 127, 136]
    candles = mk(closes, hi=[c + 1 for c in closes], lo=[c - 1 for c in closes])
    cl = [float(c) for c in closes]
    ef, es, et = ema(cl, P.ema_fast), ema(cl, P.ema_slow), ema(cl, P.ema_trend)
    warm = max(P.ema_trend, P.ema_slow, P.atr_period) + 2
    idx = None
    for i in range(warm, len(closes)):
        if None in (ef[i], es[i], et[i], ef[i - 1], es[i - 1]):
            continue
        if ef[i - 1] <= es[i - 1] and ef[i] > es[i] and cl[i] > et[i]:
            idx = i
            break
    assert idx is not None, "aucun croisement trouvé (jeu de test à revoir)"
    d = evaluate(candles[: idx + 1], None, P)
    assert d.action == Action.enter and d.reason == Reason.enter_signal
    assert d.stop < d.entry < d.take_profit


def test_sortie_stop():
    pos = PositionState(Decimal("100"), Decimal("105"), Decimal("200"), 1)
    d = evaluate(mk([100] * 12), pos, P)
    assert d.action == Action.exit and d.reason == Reason.exit_stop


def test_sortie_take_profit():
    pos = PositionState(Decimal("90"), Decimal("1"), Decimal("99"), 1)
    d = evaluate(mk([100] * 12), pos, P)
    assert d.action == Action.exit and d.reason == Reason.exit_take_profit


def test_sortie_temporelle():
    pos = PositionState(Decimal("100"), Decimal("1"), Decimal("100000"), P.max_hold)
    d = evaluate(mk([100] * 12), pos, P)
    assert d.action == Action.exit and d.reason == Reason.exit_time


def test_maintien_en_position():
    pos = PositionState(Decimal("100"), Decimal("1"), Decimal("100000"), 1)
    d = evaluate(mk([100] * 12), pos, P)
    assert d.action == Action.hold and d.reason == Reason.in_position_hold


def test_decision_serialisable():
    pos = PositionState(Decimal("100"), Decimal("105"), Decimal("200"), 1)
    d = evaluate(mk([100] * 12), pos, P)
    dd = d.to_dict()
    assert dd["action"] == "exit"
    assert dd["reason"] == "exit_stop"
    assert "snapshot" in dd and "close" in dd["snapshot"]
