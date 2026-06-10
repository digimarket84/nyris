"""Backtest mistral LONG-ONLY depuis le 1/6/2026. Reutilise entry_mistral du live (fidele).
Sorties : stop -1.5ATR, TP +4ATR, breakeven a +1R (stop->entry*1.001), reverse sur signal short.
Sizing 25E/trade, net de frais (~0.35% AR + funding 0.0003/j). Lecture seule."""
import bisect, datetime as dt
from nyris.core.database import SessionLocal
from nyris.models.asset import Asset
from nyris.services import candles as cs
from nyris.strategy.llm_engines import entry_mistral
from sqlalchemy import select

UNIV=["NEAR","SUI","LINK","AVAX","DOGE","PEPE","POND","BABY","HOME","LA","ZEC","WLD","ENA"]
JUNE1=int(dt.datetime(2026,6,1,tzinfo=dt.timezone.utc).timestamp()*1000)
PER_SIDE=0.001+0.0005/2+0.0005; FUND=0.0003; NOTI=25.0
db=SessionLocal()

def load(s):
    a=db.scalar(select(Asset).where(Asset.symbol==s))
    if not a or not a.binance_symbol: return None,None
    ex=cs.get_candles_paginated(a.binance_symbol,"5m",5200)
    cx=cs.get_candles_paginated(a.binance_symbol,"1h",900)
    return ex,cx

all_tr=[]
for sym in UNIV:
    ex,cx=load(sym)
    if not ex or not cx: 
        print("skip",sym); continue
    cx_ct=[c.close_time for c in cx]
    pos=None
    for i in range(60,len(ex)):
        bar=ex[i]; hi=float(bar.high); lo=float(bar.low); cl=float(bar.close); ct=bar.close_time
        # contexte 1h aligne (derniere bougie 1h close <= ct)
        k=bisect.bisect_right(cx_ct,ct)-1
        if k<40: continue
        exw=ex[max(0,i-299):i+1]; cxw=cx[max(0,k-79):k+1]
        sig=entry_mistral(exw,cxw)
        had=pos is not None
        if had:
            R=pos["R"]; exitp=None; reason=None
            if not pos["be"] and hi>=pos["entry"]+1.0*R:
                ns=pos["entry"]*1.001
                if ns>pos["stop"]: pos["stop"]=ns
                pos["be"]=True
            if lo<=pos["stop"]:
                exitp=pos["stop"]; reason="be_stop" if pos["be"] else "stop"
            elif hi>=pos["tp"]:
                exitp=pos["tp"]; reason="tp"
            elif sig is not None and sig.side=="short":
                exitp=cl; reason="reverse"
            if exitp is not None:
                days=max((ct-pos["ct"])/86400000,0.0)
                net=(exitp/pos["entry"]-1)-2*PER_SIDE-FUND*days
                all_tr.append({"sym":sym,"ret":net,"reason":reason,"ct":pos["ct"]})
                pos=None
        if not had and pos is None and ct>=JUNE1 and sig is not None and sig.side=="long":
            pos={"entry":cl,"stop":sig.stop,"tp":sig.tp,"R":cl-sig.stop,"ct":ct,"be":False}

import statistics as st
n=len(all_tr)
print("=== mistral LONG-only depuis 1/6/2026 (13 alts, 25E/trade) ===")
if n:
    nets=[t["ret"]*NOTI for t in all_tr]
    wins=[x for x in nets if x>0]; gp=sum(wins); gl=-sum(x for x in nets if x<0)
    print("trades=%d  win=%.0f%%  net=%+.2fE  moy=%+.3fE  PF=%.2f  [%.2f..%+.2f]"%(
        n,100*len(wins)/n,sum(nets),sum(nets)/n,gp/gl if gl else 999,min(nets),max(nets)))
    from collections import Counter
    print("sorties:",dict(Counter(t["reason"] for t in all_tr)))
    print("par actif (net E):")
    syms={}
    for t in all_tr: syms[t["sym"]]=syms.get(t["sym"],0)+t["ret"]*NOTI
    for s,v in sorted(syms.items(),key=lambda z:-z[1]): print("  %-6s %+.2f"%(s,v))
else:
    print("aucun trade")
