"""pump.fun : a partir de combien de % de gain les devs dumpent. Dev = 1er acheteur. Lecture seule."""
import json, urllib.request, statistics as st, datetime as dt
TOK=[l.strip().split("=",1)[1] for l in open("/srv/nyris/config/.env") if l.startswith("BITQUERY_TOKEN=")][0]
def q(query):
    req=urllib.request.Request("https://streaming.bitquery.io/eap",
        data=json.dumps({"query":query}).encode(),method="POST",
        headers={"Content-Type":"application/json","Authorization":f"Bearer {TOK}"})
    return json.loads(urllib.request.urlopen(req,timeout=90).read())
SOLS=["11111111111111111111111111111111","So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]
NIN="[\"%s\",\"%s\",\"%s\"]"%(SOLS[0],SOLS[1],SOLS[2])
def parse(t): return dt.datetime.fromisoformat(t.replace("Z","+00:00"))

# Tnow = derniere bougie pump dispo
c=q("""{ Solana { DEXTradeByTokens(where:{Trade:{Dex:{ProtocolName:{is:\"pump\"}}}}
     limit:{count:1} orderBy:{descending:Block_Time}) { Block{Time} } } }""")
Tnow=parse(c["data"]["Solana"]["DEXTradeByTokens"][0]["Block"]["Time"])
print("Tnow =",Tnow.isoformat())

# Phase 1 : mints depuis des fenetres relatives a Tnow (tokens ayant eu le temps de dumper)
mints=[]
for dh in [1,2,3,4,5]:
    a=(Tnow-dt.timedelta(hours=dh)).strftime("%Y-%m-%dT%H:%M:%SZ")
    b=(Tnow-dt.timedelta(hours=dh)+dt.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    c=q("""{ Solana { DEXTradeByTokens(
      where:{Block:{Time:{after:\"%s\" before:\"%s\"}}
             Trade:{Dex:{ProtocolName:{is:\"pump\"}} Currency:{MintAddress:{notIn:%s}}}}
      limit:{count:150}) { Trade{Currency{MintAddress}} } } }"""%(a,b,NIN))
    got=[r["Trade"]["Currency"]["MintAddress"] for r in c.get("data",{}).get("Solana",{}).get("DEXTradeByTokens") or []]
    new=[m for m in got if m not in mints]; mints+=new
    print("  -%dh (%s): +%d mints (total %d)"%(dh,a[11:16],len(new),len(mints)))
print("mints collectes:",len(mints))

# Phase 2 : reconstruction du dump dev par mint (scope = fiable)
dumps=[];secs=[];fracs=[];peaks=[];nsold=0;nheld=0;nbad=0
for i,M in enumerate(mints[:150]):
    try:
        t=q("""{ Solana { DEXTradeByTokens(
          where:{Trade:{Currency:{MintAddress:{is:\"%s\"}}}}
          orderBy:{ascending:Block_Time} limit:{count:600}) {
          Block{Time} Trade{Side{Type} Price Amount Account{Owner}} } } }"""%M)
        rows=t.get("data",{}).get("Solana",{}).get("DEXTradeByTokens") or []
        buys=[r for r in rows if r["Trade"]["Side"]["Type"]=="buy"]
        if len(rows)<5 or not buys: nbad+=1; continue
        dev=buys[0]["Trade"]["Account"]["Owner"];P0=buys[0]["Trade"]["Price"];t0=parse(buys[0]["Block"]["Time"])
        if P0<=0: nbad+=1; continue
        prices=[r["Trade"]["Price"] for r in rows if r["Trade"]["Price"]>0]
        peaks.append(max(prices)/P0-1)
        dbamt=sum(float(r["Trade"]["Amount"]) for r in buys if r["Trade"]["Account"]["Owner"]==dev)
        dsell=[r for r in rows if r["Trade"]["Side"]["Type"]=="sell" and r["Trade"]["Account"]["Owner"]==dev]
        if not dsell: nheld+=1; continue
        nsold+=1; f=dsell[0]
        dumps.append(f["Trade"]["Price"]/P0-1)
        secs.append((parse(f["Block"]["Time"])-t0).total_seconds())
        dsamt=sum(float(r["Trade"]["Amount"]) for r in dsell)
        fracs.append(min(dsamt/dbamt,1.0) if dbamt>0 else None)
    except Exception:
        nbad+=1
def pct(a,p):
    a=sorted(a);k=(len(a)-1)*p/100;f=int(k);return a[f] if f+1>=len(a) else a[f]+(a[f+1]-a[f])*(k-f)
print();print("=== RESULTATS (tokens exploitables=%d, ecartes=%d) ==="%(nsold+nheld,nbad))
tot=max(nsold+nheld,1)
print("dev a DUMP: %d (%.0f%%) | dev tient/pas vu vendre: %d (%.0f%%)"%(nsold,100*nsold/tot,nheld,100*nheld/tot))
if dumps:
    fr=[f for f in fracs if f is not None]
    print();print("--- GAIN %% au 1er dump du dev (n=%d) ---"%len(dumps))
    print("  mediane=%+.0f%%  moyenne=%+.0f%%  p25=%+.0f%%  p75=%+.0f%%  p90=%+.0f%%"%(
        100*st.median(dumps),100*sum(dumps)/len(dumps),100*pct(dumps,25),100*pct(dumps,75),100*pct(dumps,90)))
    print("  dump a PERTE (<0%%): %.0f%% des cas"%(100*sum(1 for d in dumps if d<0)/len(dumps)))
    print("--- TIMING buy->dump: mediane=%.0fs  p90=%.0fs  <60s: %.0f%%  <300s: %.0f%%"%(
        st.median(secs),pct(secs,90),100*sum(1 for s in secs if s<60)/len(secs),100*sum(1 for s in secs if s<300)/len(secs)))
    print("--- FRACTION position dumpee (mediane)=%.0f%%"%(100*st.median(fr) if fr else 0))
    print("--- gain MAX dispo peak/entree-dev (mediane)=%+.0f%%"%(100*st.median(peaks)))
