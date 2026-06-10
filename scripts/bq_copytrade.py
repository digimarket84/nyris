import json, urllib.request, statistics as st
TOK=[l.strip().split("=",1)[1] for l in open("/srv/nyris/config/.env") if l.startswith("BITQUERY_TOKEN=")][0]
def q(query):
    req=urllib.request.Request("https://streaming.bitquery.io/eap",
        data=json.dumps({"query":query}).encode(),method="POST",
        headers={"Content-Type":"application/json","Authorization":f"Bearer {TOK}"})
    return json.loads(urllib.request.urlopen(req,timeout=90).read())
SOLS=["11111111111111111111111111111111","So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]
NIN="[\"%s\",\"%s\",\"%s\"]"%(SOLS[0],SOLS[1],SOLS[2])
WALLETS=["omegoMAe","2CQgjcdN","FYTVwP5h","2h226QZj","4JwcPbdN","DbEh3Yah","2sapuxSm","DQApNebk"]
# il me faut les adresses completes -> on relance le classement et on garde adresses
import datetime as dt
c=q("""{ Solana { DEXTradeByTokens(where:{Trade:{Dex:{ProtocolName:{is:\"pump\"}}}} limit:{count:1} orderBy:{descending:Block_Time}){Block{Time}} } }""")
Tnow=c["data"]["Solana"]["DEXTradeByTokens"][0]["Block"]["Time"]
T0=(dt.datetime.fromisoformat(Tnow.replace("Z","+00:00"))-dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
r=q("""{ Solana { DEXTradeByTokens(
  where:{Block:{Time:{after:\"%s\"}} Trade:{Dex:{ProtocolName:{is:\"pump\"}} Currency:{MintAddress:{notIn:%s}}}}
  limit:{count:10} orderBy:{descendingByField:\"sold\"}) {
  Trade{Account{Owner}} bought: sum(of: Trade_Side_Amount, if:{Trade:{Side:{Type:{is:buy}}}})
  sold: sum(of: Trade_Side_Amount, if:{Trade:{Side:{Type:{is:sell}}}}) } } }"""%(T0,NIN))
addrs=[x["Trade"]["Account"]["Owner"] for x in r["data"]["Solana"]["DEXTradeByTokens"]]
print("wallets cibles:",len(addrs))

# Pour chaque wallet : par token, SOL achete vs vendu -> leur ret par token
their=[]   # ret par token (clos) du wallet
for w in addrs:
    rr=q("""{ Solana { DEXTradeByTokens(
      where:{Block:{Time:{after:\"%s\"}}
             Trade:{Dex:{ProtocolName:{is:\"pump\"}} Currency:{MintAddress:{notIn:%s}}
                    Account:{Owner:{is:\"%s\"}}}}
      limit:{count:150}) {
      Trade{Currency{MintAddress}}
      bought: sum(of: Trade_Side_Amount, if:{Trade:{Side:{Type:{is:buy}}}})
      sold: sum(of: Trade_Side_Amount, if:{Trade:{Side:{Type:{is:sell}}}}) } } }"""%(T0,NIN,w))
    for x in rr.get("data",{}).get("Solana",{}).get("DEXTradeByTokens") or []:
        b=float(x.get("bought") or 0); s=float(x.get("sold") or 0)
        if b>0.05 and s>0:   # position cloturee, taille minimale
            their.append(s/b-1)
print("trades (wallet x token) clotures analyses:",len(their))
def med(a): return st.median(a) if a else 0
print("\n--- LEUR perf par trade (sans nous) ---")
print("  ret median=%+.1f%%  moyenne=%+.1f%%  %%gagnants=%.0f%%"%(100*med(their),100*sum(their)/len(their),100*sum(1 for x in their if x>0)/len(their)))

# COPY avec slippage symetrique s : notre ret ~ (sell*(1-s))/(buy*(1+s)) - 1 - cout
COST=0.01  # 1% frais/slippage de base cote Solana
print("\n--- SI ON COPIE (selon notre desavantage de latence/slippage s) ---")
print("  s=desavantage par cote (le prix bouge entre eux et nous)")
for s in (0.0,0.02,0.05,0.10,0.15):
    ours=[ (1+r)*(1-s)/(1+s) - 1 - COST for r in their ]
    tot=sum(ours)
    print("  s=%4.0f%% : notre ret median=%+.1f%%  total cumule=%+.1f (sur %d copies)  %%gagnants=%.0f%%"%(
        100*s,100*med(ours),tot,len(ours),100*sum(1 for x in ours if x>0)/len(ours)))
