"""Univers meanrev-v3 = univers v2 (100 paires USDT) SANS les majors (MR faible sur eux)."""
from nyris.strategy.meanrev_v2_universe import PAIRS as _V2

MAJORS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
PAIRS = tuple(p for p in _V2 if p not in MAJORS)
