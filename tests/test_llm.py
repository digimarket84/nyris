"""Smoke tests des 4 stratégies LLM : registre cohérent + aucun signal (ni crash) à plat."""

from decimal import Decimal

from nyris.strategy.llm_engines import ENTRY_FNS, STRATEGIES
from nyris.strategy.models import Candle


def mk(n, price=100.0):
    out = []
    for i in range(n):
        p = Decimal(str(price))
        out.append(Candle(i * 60000, (i + 1) * 60000, p, p + 1, p - 1, p, Decimal("1")))
    return out


def test_registry_coherent():
    names = {s.name for s in STRATEGIES}
    assert names == set(ENTRY_FNS) == {"perplexity", "chatgpt", "gemini", "mistral"}
    for s in STRATEGIES:
        assert s.run_id.startswith("live-") and s.exec_tf and s.ctx_tf


def test_no_signal_and_no_crash_on_flat():
    ex, cx = mk(320), mk(320)
    for fn in ENTRY_FNS.values():
        assert fn(ex, cx) is None  # marché plat -> pas de signal, pas d'exception
