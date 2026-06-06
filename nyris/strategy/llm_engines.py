"""Fonctions d'entrée pures des 4 stratégies LLM (fidèles aux specs fournies).

Chaque fonction évalue la DERNIÈRE bougie clôturée du timeframe d'exécution et renvoie
un LlmSignal (long/short + entry/stop/tp) ou None. Entrée = clôture de la bougie signal
(approx de "open de la suivante", quasi continu en crypto). Indicateurs purs (indicators).
"""

from __future__ import annotations

from nyris.strategy.indicators import adx, atr, bollinger, donchian, ema, rsi, sma
from nyris.strategy.llm_models import LlmSignal, LlmStrategy


def _cols(candles):
    o = [float(c.open) for c in candles]
    h = [float(c.high) for c in candles]
    low = [float(c.low) for c in candles]
    c = [float(c.close) for c in candles]
    v = [float(c.volume) for c in candles]
    return o, h, low, c, v


def _closes(candles):
    return ([float(x.close) for x in candles], [float(x.high) for x in candles],
            [float(x.low) for x in candles])


# ---------- 1) Perplexity : Range Reversion BB-RSI-ADX (15m + 1h) ----------
def entry_perplexity(ex, cx):
    if len(ex) < 30 or len(cx) < 205:
        return None
    o, h, low, c, v = _cols(ex)
    c1, h1, l1 = _closes(cx)
    adx1 = adx(h1, l1, c1, 14)
    sma200 = sma(c1, 200)
    j = len(cx) - 1
    if None in (adx1[j], sma200[j]):
        return None
    if adx1[j] >= 22 or abs(c1[j] - sma200[j]) / sma200[j] > 0.08:
        return None
    mid, up, lo = bollinger(c, 20, 2.0)
    r = rsi(c, 14)
    a = atr(h, low, c, 14)
    vs = sma(v, 20)
    i = len(ex) - 1
    if None in (mid[i], up[i], lo[i], lo[i - 1], up[i - 1], r[i], r[i - 1], a[i], vs[i]):
        return None
    atrp = a[i] / c[i]
    rng = h[i] - low[i]
    if not (0.0035 <= atrp <= 0.022 and (up[i] - lo[i]) / c[i] >= 0.009):
        return None
    if rng <= 0 or abs(c[i] - o[i]) / rng < 0.20 or v[i] < 0.8 * vs[i]:
        return None
    inside = lo[i] <= c[i] <= up[i]
    entry = c[i]
    sd = 1.35 * a[i]
    if sd / entry < 0.0045:
        return None
    if (c[i - 1] < lo[i - 1] and inside and r[i - 1] < 28 and r[i] > 30
            and c[i] > low[i] + 0.35 * rng):
        return LlmSignal("long", entry, entry - sd, mid[i],
                         "enter_long_meanrev", entry + 2.2 * sd)
    if (c[i - 1] > up[i - 1] and inside and r[i - 1] > 72 and r[i] < 70
            and c[i] < low[i] + 0.65 * rng):
        return LlmSignal("short", entry, entry + sd, mid[i],
                         "enter_short_meanrev", entry - 2.2 * sd)
    return None


# ---------- 2) ChatGPT : ATR Pullback Continuation (15m + 4h) ----------
def entry_chatgpt(ex, cx):
    if len(ex) < 40 or len(cx) < 212:
        return None
    o, h, low, c, v = _cols(ex)
    c4, h4, l4 = _closes(cx)
    e200 = ema(c4, 200)
    adx4 = adx(h4, l4, c4, 14)
    j = len(cx) - 1
    if None in (e200[j], e200[j - 10], adx4[j]) or adx4[j] <= 25:
        return None
    e20 = ema(c, 20)
    r2 = rsi(c, 2)
    a = atr(h, low, c, 14)
    vs = sma(v, 20)
    i = len(ex) - 1
    if None in (e20[i - 1], r2[i - 1], a[i], vs[i]) or a[i] / c[i] <= 0.0035:
        return None
    entry = c[i]
    A = a[i]
    long_tr = c4[j] > e200[j] and e200[j] > e200[j - 10] and c4[j] < e200[j] * 1.15
    short_tr = c4[j] < e200[j] and e200[j] < e200[j - 10] and c4[j] > e200[j] * 0.85
    if (long_tr and r2[i - 1] <= 5 and min(low[i - 1], low[i - 2], low[i - 3]) <= e20[i - 1]
            and c[i] > h[i - 1] and v[i] > 1.2 * vs[i]):
        return LlmSignal("long", entry, entry - 1.8 * A, entry + 3.6 * A, "enter_long_apc")
    if (short_tr and r2[i - 1] >= 95 and max(h[i - 1], h[i - 2], h[i - 3]) >= e20[i - 1]
            and c[i] < low[i - 1] and v[i] > 1.2 * vs[i]):
        return LlmSignal("short", entry, entry + 1.8 * A, entry - 3.6 * A, "enter_short_apc")
    return None


# ---------- 3) Gemini : Volatility Expansion Breakout (15m + 4h) ----------
def entry_gemini(ex, cx):
    if len(ex) < 130 or len(cx) < 55:
        return None
    o, h, low, c, v = _cols(ex)
    c4 = [float(x.close) for x in cx]
    e50 = ema(c4, 50)
    j = len(cx) - 1
    if e50[j] is None:
        return None
    dch, dcl = donchian(h, low, 20)
    a = atr(h, low, c, 14)
    ad = adx(h, low, c, 14)
    vs = sma(v, 20)
    i = len(ex) - 1
    if None in (dch[i], dcl[i], a[i], ad[i], vs[i]):
        return None
    am = [a[k] for k in range(max(0, i - 100), i) if a[k] is not None]
    if not am:
        return None
    if a[i] < 1.2 * (sum(am) / len(am)) or ad[i] <= 25 or v[i] <= 1.8 * vs[i]:
        return None
    entry = c[i]
    rr = 2.0 * a[i]
    if c4[j] > e50[j] and c[i] >= dch[i]:
        return LlmSignal("long", entry, entry - rr, entry + 3 * rr, "enter_long_breakout")
    if c4[j] < e50[j] and c[i] <= dcl[i]:
        return LlmSignal("short", entry, entry + rr, entry - 3 * rr, "enter_short_breakout")
    return None


# ---------- 4) Mistral : BB-RSI Mean Reversion (5m + 1h) ----------
def entry_mistral(ex, cx):
    if len(ex) < 30 or len(cx) < 30:
        return None
    o, h, low, c, v = _cols(ex)
    c1, h1, l1 = _closes(cx)
    adx1 = adx(h1, l1, c1, 14)
    j = len(cx) - 1
    if adx1[j] is None or adx1[j] >= 25:
        return None
    mid, up, lo = bollinger(c, 20, 2.0)
    r = rsi(c, 14)
    a = atr(h, low, c, 14)
    vs = sma(v, 20)
    i = len(ex) - 1
    if None in (up[i], lo[i], r[i], a[i], vs[i]):
        return None
    atrp = a[i] / c[i]
    hour = (ex[i].close_time // 3_600_000) % 24
    if not (0.005 < atrp < 0.05 and 8 <= hour < 20 and v[i] > 1.5 * vs[i]):
        return None
    entry = c[i]
    A = a[i]
    if c[i] <= lo[i] and r[i] < 30:
        return LlmSignal("long", entry, entry - 1.5 * A, entry + 4 * A, "enter_long_meanrev")
    if c[i] >= up[i] and r[i] > 70:
        return LlmSignal("short", entry, entry + 1.5 * A, entry - 4 * A, "enter_short_meanrev")
    return None


ENTRY_FNS = {
    "perplexity": entry_perplexity,
    "chatgpt": entry_chatgpt,
    "gemini": entry_gemini,
    "mistral": entry_mistral,
}

# be_trigger_r en multiples de R (=|entry-stop|) : chatgpt 1 ATR=R/1.8=0.556 ; gemini 1.5R ;
# mistral 1.5 ATR=1.0R ; perplexity : BE après TP1 (géré à part).
STRATEGIES = [
    LlmStrategy("perplexity", "live-perplexity-v1", "15m", "1h", 320, 320,
                reward_ratio=2.2, be_trigger_r=0.0, partial=True,
                max_hold_bars=8, cooldown_bars=12, max_open_positions=3),
    LlmStrategy("chatgpt", "live-chatgpt-v1", "15m", "4h", 320, 320,
                reward_ratio=2.0, be_trigger_r=0.556, be_offset_pct=0.0,
                max_open_positions=3),
    # gemini ARRÊTÉ (retiré de la liste, réversible) : breakout sur tokens hypés -> pertes
    # unitaires énormes (stops ATR ~8%). entry_gemini reste dispo pour réactivation.
    LlmStrategy("mistral", "live-mistral-v1", "5m", "1h", 320, 320,
                reward_ratio=2.667, be_trigger_r=1.0, be_offset_pct=0.001,
                reverse_on_opposite=True, max_open_positions=3),
]
