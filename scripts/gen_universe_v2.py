"""Genere la liste d'univers meanrev-v2 : top ~100 paires USDT liquides (>2M$/j, historique>=40j)."""
import json
import urllib.request

from nyris.services import candles as cs

STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "AEUR", "EUR", "EURI",
           "USD1", "XUSD", "GUSD", "PYUSD", "USDE", "RLUSD", "BFUSD"}
# or/wrapped : pas notre domaine de mean-reversion crypto
EXCLUDE = {"PAXG", "XAUT", "WBTC"}

t = json.loads(urllib.request.urlopen(
    "https://api.binance.com/api/v3/ticker/24hr", timeout=30).read())
cand = []
for x in t:
    s = x["symbol"]
    if not s.endswith("USDT"):
        continue
    base = s[:-4]
    if not base.isascii():            # symboles non-ASCII (scam/junk)
        continue
    if base in STABLES or base in EXCLUDE or base.endswith("USD"):
        continue
    if any(s.endswith(suf + "USDT") for suf in ("UP", "DOWN", "BULL", "BEAR")):
        continue
    if float(x["quoteVolume"]) >= 2_000_000:
        cand.append(s)
cand.sort(key=lambda sym: -float(
    next(z for z in t if z["symbol"] == sym)["quoteVolume"]))

keep = []
for s in cand[:130]:
    try:
        if len(cs.get_candles(s, "1d", 60)) >= 40:
            keep.append(s)
    except Exception:
        pass
    if len(keep) >= 100:
        break

print(f"# univers v2 : {len(keep)} paires")
print("PAIRS = (")
line = "    "
for s in keep:
    add = '"' + s + '", '
    if len(line) + len(add) > 92:
        print(line)
        line = "    "
    line += add
if line.strip():
    print(line)
print(")")
