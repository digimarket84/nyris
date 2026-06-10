"""pump.fun : compare 2 profils de dump sur le MEME echantillon.
A) Premier acheteur (sniper)  B) Plus gros vendeur (vrai rugger : largue le plus de supply).
Dev/rugger gains mesures vs leur entree ET vs le prix de lancement du token. Lecture seule."""
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
def med(a): return st.median(a) if a else 0
def pct(a,p):
    if not a: return 0
    a=sorted(a);k=(len(a)-1)*p/100;f=int(k);return a[f] if f+1>=len(a) else a[f]+(a[f+1]-a[f])*(k-f)

c=q("""{ Solana { DEXTradeByTokens(where:{Trade:{Dex:{ProtocolName:{is:\"pump\"}}}}
     limit:{count:1} orderBy:{descending:Block_Time}) { Block{Time} } } }""")
Tnow=parse(c["data"]["Solana"]["DEXTradeByTokens"][0]["Block"]["Time"])
mints=[]
for dh in [1,2,3,4,5]:
    a=(Tnow-dt.timedelta(hours=dh)).strftime("%Y-%m-%dT%H:%M:%SZ")
    b=(Tnow-dt.timedelta(hours=dh)+dt.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    c=q("""{ Solana { DEXTradeByTokens(where:{Block:{Time:{after:\"%s\" before:\"%s\"}}
        Trade:{Dex:{ProtocolName:{is:\"pump\"}} Currency:{MintAddress:{notIn:%s}}}}
        limit:{count:150}) { Trade{Currency{MintAddress}} } } }"""%(a,b,NIN))
    for r in c.get("data",{}).get("Solana",{}).get("DEXTradeByTokens") or []:
        m=r["Trade"]["Currency"]["MintAddress"]
        if m not in mints: mints.append(m)
print("Tnow=%s | mints=%d"%(Tnow.isoformat(),len(mints)))

# A) sniper
A_gain=[];A_sec=[]
# B) rugger (plus gros vendeur)
B_gain_launch=[];B_sec=[];B_share=[];B_vs_peak=[];B_has_buy=0;B_n=0;same=0
for M in mints[:150]:
    try:
        t=q("""{ Solana { DEXTradeByTokens(where:{Trade:{Currency:{MintAddress:{is:\"%s\"}}}}
            orderBy:{ascending:Block_Time} limit:{count:800}) {
            Block{Time} Trade{Side{Type} Price Amount Account{Owner}} } } }"""%M)
        rows=t.get("data",{}).get("Solana",{}).get("DEXTradeByTokens") or []
        buys=[r for r in rows if r["Trade"]["Side"]["Type"]=="buy"]
        sells=[r for r in rows if r["Trade"]["Side"]["Type"]=="sell"]
        if len(rows)<5 or not buys or not sells: continue
        P0=buys[0]["Trade"]["Price"]
        if P0<=0: continue
        peak=max(r["Trade"]["Price"] for r in rows if r["Trade"]["Price"]>0)
        # A) sniper = premier acheteur
        sniper=buys[0]["Trade"]["Account"]["Owner"]; t0=parse(buys[0]["Block"]["Time"])
        sdump=[r for r in rows if r["Trade"]["Side"]["Type"]=="sell" and r["Trade"]["Account"]["Owner"]==sniper]
        if sdump:
            A_gain.append(sdump[0]["Trade"]["Price"]/P0-1)
            A_sec.append((parse(sdump[0]["Block"]["Time"])-t0).total_seconds())
        # B) rugger = plus gros vendeur (par volume vendu)
        tot_sell={}
        for r in sells:
            o=r["Trade"]["Account"]["Owner"]; tot_sell[o]=tot_sell.get(o,0)+float(r["Trade"]["Amount"])
        rugger=max(tot_sell,key=tot_sell.get)
        total_all=sum(tot_sell.values())
        rsells=[r for r in sells if r["Trade"]["Account"]["Owner"]==rugger]
        vol=sum(float(r["Trade"]["Amount"]) for r in rsells)
        wavg=sum(r["Trade"]["Price"]*float(r["Trade"]["Amount"]) for r in rsells)/vol  # prix moyen pondere de vente
        B_n+=1
        B_gain_launch.append(wavg/P0-1)
        B_share.append(tot_sell[rugger]/total_all if total_all>0 else 0)
        B_vs_peak.append(wavg/peak)
        B_sec.append((parse(rsells[0]["Block"]["Time"])-t0).total_seconds())
        if any(r["Trade"]["Account"]["Owner"]==rugger for r in buys): B_has_buy+=1
        if rugger==sniper: same+=1
    except Exception:
        pass
print();print("=== COMPARAISON (tokens analyses A=%d, B=%d) ==="%(len(A_gain),B_n))
print();print("--- A) PREMIER ACHETEUR (sniper) ---")
print("  gain vs son entree : mediane=%+.0f%% p25=%+.0f%% p75=%+.0f%%"%(100*med(A_gain),100*pct(A_gain,25),100*pct(A_gain,75)))
print("  delai dump : mediane=%.0fs  <60s=%.0f%%"%(med(A_sec),100*sum(1 for s in A_sec if s<60)/max(len(A_sec),1)))
print();print("--- B) PLUS GROS VENDEUR (vrai rugger) ---")
print("  largue le token a : mediane=%+.0f%% du prix de lancement (p25=%+.0f%% p75=%+.0f%% p90=%+.0f%%)"%(
    100*med(B_gain_launch),100*pct(B_gain_launch,25),100*pct(B_gain_launch,75),100*pct(B_gain_launch,90)))
print("  vend a %.0f%% du pic (mediane) -> %s"%(100*med(B_vs_peak),"pres du top" if med(B_vs_peak)>0.7 else "bien avant le top"))
print("  part du supply vendu qu il represente : mediane=%.0f%%"%(100*med(B_share)))
print("  delai lancement->son 1er gros dump : mediane=%.0fs (p90=%.0fs)"%(med(B_sec),pct(B_sec,90)))
print("  a un achat visible (vs allocation gratuite) : %.0f%%"%(100*B_has_buy/max(B_n,1)))
print("  rugger == sniper (meme wallet) : %.0f%% des tokens"%(100*same/max(B_n,1)))
