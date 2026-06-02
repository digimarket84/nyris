"""Validation/tuning BORNÉE de la stratégie (anti curve-fitting).

Principe : un petit jeu de variantes (une-variable-à-la-fois autour d'une
baseline + 2 candidats combinés), pas de grid search massif. Split chronologique
in-sample / out-of-sample (70/30) pour juger la robustesse.

Exécution : python -m nyris.strategy.validate
"""

from __future__ import annotations

from decimal import Decimal

from nyris.strategy.backtest import run_backtest, summarize, timeframe_hours
from nyris.strategy.models import StrategyParams

BASE_CAP = Decimal("1000")
ASSETS = ["BTC", "ETH", "SOL"]
IS_RATIO = 0.7


def _v(name: str, **over) -> tuple[str, StrategyParams]:
    return name, StrategyParams(**over)


def variants_4h() -> list[tuple[str, StrategyParams]]:
    tf = "4h"
    return [
        _v("baseline", timeframe=tf),  # trend200, 20/50, atr2.0, R2.0, hold60
        _v("trend100", timeframe=tf, ema_trend=100),
        _v("ema_10_30", timeframe=tf, ema_fast=10, ema_slow=30),
        _v("ema_12_26", timeframe=tf, ema_fast=12, ema_slow=26),
        _v("atr_1.5", timeframe=tf, atr_stop_mult=1.5),
        _v("atr_2.5", timeframe=tf, atr_stop_mult=2.5),
        _v("reward_1.5", timeframe=tf, reward_r=1.5),
        _v("hold_40", timeframe=tf, max_hold=40),
        # 2 candidats combinés (plus actifs, sans trahir la philosophie)
        _v(
            "cand_active", timeframe=tf, ema_trend=100, ema_fast=10, ema_slow=30,
            reward_r=1.5, max_hold=40,
        ),
        _v("cand_moderate", timeframe=tf, ema_trend=100, ema_fast=12, ema_slow=26),
    ]


def variants_1h() -> list[tuple[str, StrategyParams]]:
    return [
        _v("baseline_1h", timeframe="1h"),
        _v(
            "cand_active_1h", timeframe="1h", ema_trend=100, ema_fast=10,
            ema_slow=30, reward_r=1.5, max_hold=40,
        ),
    ]


def _warmup(p: StrategyParams) -> int:
    return max(p.ema_trend, p.ema_slow, p.atr_period) + 2


def run_suite(variants, data: dict[str, list]) -> dict:
    assets = list(data.keys())
    ref = data[assets[0]]  # actifs alignés dans le temps : BTC sert de référence
    out: dict = {}
    for name, params in variants:
        warm = _warmup(params)
        tf_h = timeframe_hours(params.timeframe)
        if len(ref) <= warm + 5:
            out[name] = {"error": "pas assez de bougies"}
            continue
        start_ms = ref[warm].close_time
        end_ms = ref[-1].close_time
        split_ms = ref[warm + int((len(ref) - warm) * IS_RATIO)].close_time

        per_asset: dict = {}
        pooled: list = []
        for sym in assets:
            trades = run_backtest(data[sym], params, BASE_CAP, compounding=False).trades
            pooled += trades
            is_t = [t for t in trades if t["entry_time"] < split_ms]
            oos = [t for t in trades if t["entry_time"] >= split_ms]
            per_asset[sym] = {
                "full": summarize(trades, BASE_CAP, end_ms - start_ms, tf_h),
                "is": summarize(is_t, BASE_CAP, split_ms - start_ms, tf_h),
                "oos": summarize(oos, BASE_CAP, end_ms - split_ms, tf_h),
            }

        agg_cap = BASE_CAP * len(assets)
        out[name] = {
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
            "aggregate": {
                "full": summarize(pooled, agg_cap, end_ms - start_ms, tf_h),
                "is": summarize(
                    [t for t in pooled if t["entry_time"] < split_ms],
                    agg_cap, split_ms - start_ms, tf_h,
                ),
                "oos": summarize(
                    [t for t in pooled if t["entry_time"] >= split_ms],
                    agg_cap, end_ms - split_ms, tf_h,
                ),
            },
        }
    return out


def _fmt(v) -> str:
    return "—" if v is None else str(v)


def print_table(tf: str, suite: dict) -> None:
    print(f"\n=== {tf} — agrégé BTC+ETH+SOL (notional fixe) ===")
    print(
        f"{'variante':14} {'n':>4} {'t/mois':>7} {'PF':>6} {'win%':>6} {'avgR':>6} "
        f"{'ret%':>8} {'dd%':>6} | OOS {'n':>3} {'PF':>6} {'ret%':>8}"
    )
    for name, info in suite.items():
        if "aggregate" not in info:
            print(f"{name:14} {info.get('error', '?')}")
            continue
        f = info["aggregate"]["full"]
        o = info["aggregate"]["oos"]
        win = round(f["win_rate"] * 100, 1)
        print(
            f"{name:14} {f['n_trades']:>4} {_fmt(f['trades_per_month']):>7} "
            f"{_fmt(f['profit_factor']):>6} {win:>6} {_fmt(f['avg_r']):>6} "
            f"{_fmt(f['total_return_pct']):>8} {_fmt(f['max_drawdown_pct']):>6} | "
            f"    {o['n_trades']:>3} {_fmt(o['profit_factor']):>6} {_fmt(o['total_return_pct']):>8}"
        )


def _main() -> None:
    import json

    from nyris.services import candles as candles_service

    report: dict = {}

    data_4h = {s: candles_service.get_candles(f"{s}EUR", "4h", 1000) for s in ASSETS}
    report["4h"] = run_suite(variants_4h(), data_4h)
    print_table("4h", report["4h"])

    data_1h = {s: candles_service.get_candles(f"{s}EUR", "1h", 1000) for s in ASSETS}
    report["1h"] = run_suite(variants_1h(), data_1h)
    print_table("1h", report["1h"])

    out_path = "/srv/nyris/backups/validation.json"
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nExport JSON complet : {out_path}")
    except OSError as exc:
        print(f"\n(Export JSON impossible : {exc})")


if __name__ == "__main__":
    _main()
