"""Collecteur PAPER forward copy-trade pump.fun (temps reel via Bitquery WS).
Copie 8 wallets gagnants. 3 scenarios de slippage (notre desavantage de latence). Zero SOL reel."""
import asyncio, json, time, websockets
TOK=[l.strip().split("=",1)[1] for l in open("/srv/nyris/config/.env") if l.startswith("BITQUERY_TOKEN=")][0]
WALLETS=json.load(open("/tmp/wallets.json"))
URL="wss://streaming.bitquery.io/eap?token="+TOK
SOLS=["11111111111111111111111111111111","So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]
SLIPS=[0.0,0.05,0.10]; COST=0.01; MAX_SECONDS=6*3600
WL="[%s]"%",".join("\"%s\""%w for w in WALLETS)
NIN="[%s]"%",".join("\"%s\""%s for s in SOLS)
SUB="""subscription { Solana { DEXTradeByTokens(
  where:{Trade:{Dex:{ProtocolName:{is:\"pump\"}} Account:{Owner:{in:%s}} Currency:{MintAddress:{notIn:%s}}}}
  limit:{count:20}) { Trade{ Side{Type} Price Currency{MintAddress} Account{Owner} } } } }"""%(WL,NIN)
pos={}            # (wallet,mint) -> prix d achat brut
realized={s:[] for s in SLIPS}
nbuy=0; t0=time.time()
def snapshot(note=""):
    out={"runtime_min":round((time.time()-t0)/60,1),"buys_copies":nbuy,"open":len(pos),"scenarios":{}}
    for s in SLIPS:
        r=realized[s]; tot=sum(r); win=100*sum(1 for x in r if x>0)/len(r) if r else 0
        out["scenarios"]["slip_%d%%"%(s*100)]={"closed":len(r),"pnl_sum_pct":round(100*tot,1),"win_pct":round(win,0)}
    json.dump(out,open("/tmp/copytrade_live.json","w"),indent=2)
    print("[%s] %s"%(time.strftime("%H:%M:%S"),json.dumps(out["scenarios"])),flush=True)
async def run():
    global nbuy
    while time.time()-t0<MAX_SECONDS:
        try:
            async with websockets.connect(URL,subprotocols=["graphql-ws"],open_timeout=20,ping_interval=15) as ws:
                await ws.send(json.dumps({"type":"connection_init"}))
                await asyncio.wait_for(ws.recv(),timeout=15)
                await ws.send(json.dumps({"id":"1","type":"start","payload":{"query":SUB}}))
                print("connecte+abonne (%d wallets). Run max %dh."%(len(WALLETS),MAX_SECONDS//3600),flush=True)
                last=time.time()
                while time.time()-t0<MAX_SECONDS:
                    m=await asyncio.wait_for(ws.recv(),timeout=120)
                    d=json.loads(m)
                    if d.get("type")!="data": continue
                    for row in d["payload"]["data"]["Solana"]["DEXTradeByTokens"] or []:
                        tr=row["Trade"]; w=tr["Account"]["Owner"]; mint=tr["Currency"]["MintAddress"]
                        side=tr["Side"]["Type"]; price=tr["Price"]
                        if price<=0: continue
                        k=(w,mint)
                        if side=="buy":
                            if k not in pos: pos[k]=price; nbuy+=1
                        elif side=="sell" and k in pos:
                            buy=pos.pop(k)
                            for s in SLIPS:
                                realized[s].append((price*(1-s))/(buy*(1+s))-1-COST)
                    if time.time()-last>300:  # snapshot toutes les 5 min
                        snapshot(); last=time.time()
        except Exception as e:
            print("reconnect apres:",type(e).__name__,str(e)[:120],flush=True)
            snapshot(); await asyncio.sleep(10)
    snapshot("FIN"); print("=== FIN apres %dh ==="%(MAX_SECONDS//3600),flush=True)
asyncio.run(run())
