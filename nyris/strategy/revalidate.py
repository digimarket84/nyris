"""Revalidation de la config candidate V1.1 sur historique long (2-3 ans, 4h).

- récupère un historique étendu BTC/ETH/SOL en 4h
- backtest de V1.1 (+ baseline pour référence), sans nouveaux indicateurs
- split chronologique in-sample / out-of-sample (70/30)
- walk-forward simple : N folds chronologiques consécutifs (config FIXE, pas
  d'optimisation par fold -> pas de curve fitting), pour juger la cohérence
  inter-régimes.

Exécution : python -m nyris.strategy.revalidate
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.backtest import run_backtest, summarize, timeframe_hours
from nyris.strategy.engine import warmup
from nyris.strategy.models import StrategyParams

BASE_CAP = Decimal("1000")
ASSETS = ["BTC", "ETH", "SOL"]
N_FOLDS = 6
IS_RATIO = 0.7
TARGET_CANDLES = 6600  # ~3 ans de 4h

CONFIGS: dict[str, StrategyParams] = {
    "v1_1": StrategyParams(timeframe="4h", atr_stop_mult=1.5, reward_r=1.5),
    "baseline": StrategyParams(timeframe="4h"),
}


def _fold_bounds(start_ms: float, end_ms: float, n: int) -> list[tuple[float, float]]:
    step = (end_ms - start_ms) / n
    return [(start_ms + i * step, start_ms + (i + 1) * step) for i in range(n)]


def fold_summaries(
    trades: list[dict], start_ms: float, end_ms: float, n: int, cap: Decimal, tf_h: float
) -> list[dict]:
    out = []
    for k, (lo, hi) in enumerate(_fold_bounds(start_ms, end_ms, n)):
        if k < n - 1:
            seg = [t for t in trades if lo <= t["entry_time"] < hi]
        else:
            seg = [t for t in trades if lo <= t["entry_time"] <= hi]
        out.append({"fold": k + 1, **summarize(seg, cap, hi - lo, tf_h)})
    return out


def evaluate_config(params: StrategyParams, data: dict[str, list]) -> dict:
    tf_h = timeframe_hours(params.timeframe)
    warm = warmup(params)
    per_asset: dict = {}
    pooled: list = []
    starts: list = []
    ends: list = []

    for sym, candles in data.items():
        if len(candles) <= warm + 5:
            per_asset[sym] = {"error": "historique insuffisant", "n_candles": len(candles)}
            continue
        trades = run_backtest(candles, params, BASE_CAP, compounding=False).trades
        pooled += trades
        s = candles[warm].close_time
        e = candles[-1].close_time
        starts.append(s)
        ends.append(e)
        split = s + int((e - s) * IS_RATIO)
        is_t = [t for t in trades if t["entry_time"] < split]
        oos_t = [t for t in trades if t["entry_time"] >= split]
        per_asset[sym] = {
            "n_candles": len(candles),
            "full": summarize(trades, BASE_CAP, e - s, tf_h),
            "is": summarize(is_t, BASE_CAP, split - s, tf_h),
            "oos": summarize(oos_t, BASE_CAP, e - split, tf_h),
        }

    cap = BASE_CAP * len(data)
    sa, ea = min(starts), max(ends)
    split = sa + int((ea - sa) * IS_RATIO)
    agg_is = [t for t in pooled if t["entry_time"] < split]
    agg_oos = [t for t in pooled if t["entry_time"] >= split]
    aggregate = {
        "full": summarize(pooled, cap, ea - sa, tf_h),
        "is": summarize(agg_is, cap, split - sa, tf_h),
        "oos": summarize(agg_oos, cap, ea - split, tf_h),
        "folds": fold_summaries(pooled, sa, ea, N_FOLDS, cap, tf_h),
    }
    return {
        "params": {
            "timeframe": params.timeframe,
            "ema_trend": params.ema_trend,
            "ema_fast": params.ema_fast,
            "ema_slow": params.ema_slow,
            "atr_stop_mult": params.atr_stop_mult,
            "reward_r": params.reward_r,
            "max_hold": params.max_hold,
        },
        "per_asset": per_asset,
        "aggregate": aggregate,
    }


def _f(v) -> str:
    return "—" if v is None else str(v)


def print_report(name: str, info: dict) -> None:
    p = info["params"]
    print(
        f"\n=== {name} (4h trend{p['ema_trend']} {p['ema_fast']}/{p['ema_slow']} "
        f"atr{p['atr_stop_mult']} R{p['reward_r']} hold{p['max_hold']}) ==="
    )
    a = info["aggregate"]
    for seg in ("full", "is", "oos"):
        s = a[seg]
        print(
            f"  {seg:4} n={s['n_trades']:>4} t/mois={_f(s['trades_per_month']):>5} "
            f"PF={_f(s['profit_factor']):>6} win%={round(s['win_rate'] * 100, 1):>5} "
            f"avgR={_f(s['avg_r']):>7} ret%={_f(s['total_return_pct']):>8} "
            f"dd%={_f(s['max_drawdown_pct']):>6}"
        )
    print("  par actif (full) :")
    for sym, pa in info["per_asset"].items():
        if "full" not in pa:
            print(f"    {sym}: {pa.get('error')} ({pa.get('n_candles')} bougies)")
            continue
        s = pa["full"]
        print(
            f"    {sym}: candles={pa['n_candles']:>5} n={s['n_trades']:>3} "
            f"PF={_f(s['profit_factor']):>6} win%={round(s['win_rate'] * 100, 1):>5} "
            f"ret%={_f(s['total_return_pct']):>8} dd%={_f(s['max_drawdown_pct']):>6}"
        )
    folds = " | ".join(
        f"F{f['fold']}:n{f['n_trades']}/PF{_f(f['profit_factor'])}/r{_f(f['total_return_pct'])}"
        for f in a["folds"]
    )
    print(f"  walk-forward ({N_FOLDS} folds agrégés) : {folds}")


def _main() -> None:
    import json

    from nyris.services import candles as candles_service

    data = {}
    for s in ASSETS:
        candles = candles_service.get_candles_paginated(f"{s}EUR", "4h", TARGET_CANDLES)
        data[s] = candles
        print(f"{s}EUR : {len(candles)} bougies 4h récupérées")

    report = {}
    for name, params in CONFIGS.items():
        info = evaluate_config(params, data)
        report[name] = info
        print_report(name, info)

    out_path = "/srv/nyris/backups/revalidation.json"
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nExport JSON : {out_path}")
    except OSError as exc:
        print(f"\n(Export impossible : {exc})")


if __name__ == "__main__":
    _main()
