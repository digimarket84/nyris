# Council Transcript — Nouvelles stratégies (2026-06-10)

## Question posée (cadrée)
Trouver une stratégie crypto à edge RÉEL out-of-sample. Données : OHLCV daily+intraday (BTC/ETH/SOL+13 alts), funding rates Binance. Déjà validé : MR-long daily sur alts (PF 1.65 OOS), trend daily (dormant). Déjà rejeté : short, intraday OHLCV, 4 strat LLM, kNN, pump.fun. Demande : 5-8 hypothèses NOUVELLES, falsifiables, backtestables, avec raison économique.

## Convergence (4 idées unanimes)
1. **Funding rates** — levier le plus négligé. Filtre sur MR existant OU signal contrarien (déleveraging forcé mean-reverte).
2. **Cross-sectionnel** — ranker les alts, long top-k/bottom-k, hebdo. La sélection EST l'edge.
3. **Vol-targeting sizing** — géométrie/risque-ajusté, pas alpha nouveau.
4. **Régime-switching** trend+MR — book toujours actif.

## Clashes
- Edge MR = réel ou régime-fit ? (Contrarian : walk-forward obligatoire)
- Long-only ? (pairs market-neutral long alt / short BTC-perp contournent le base rate)
- PF vs Sharpe/maxDD/turnover.

## Angles morts (peer review)
- Slippage sur alts FINS (paper le cache) = menace majeure sur l'edge small-cap.
- 13-16 alts = cross-section mince/bruité.
- Saisonnalité = bruit (rejeter).

## Recommandation
1) Filtre funding sur MR (besoin ingestion funding). 2) Cross-sectionnel (données en main). 3) Vol-sizing. 4) Régime-switch. Rejeter saisonnalité. Revérifier slippage. Mesurer Sharpe/maxDD.

## Première chose
Backtester le cross-sectionnel aujourd'hui + préparer l'ingestion funding pour le filtre.

---
### Réponses brutes des 5 conseillers
**First Principles (forced-flow)** : edge d'un petit trader = être la contrepartie patiente d'un flux forcé. #1 funding liquidation harvest (funding très négatif → squeeze long spot), #2 cross-sectionnel laggards, #3 calendaire (rebalancing fonds), #4 vol-targeting, #5 filtre funding. Rang 1>2>4>3>5.

**Executor (effort/promesse)** : 1) vol-targeting du MR live (1 run), 2) cross-sectional relative strength (top-3 30d, hebdo), 3) cross-sectional MR (bottom-3 5d), 4) funding carry/contrarian (besoin ingestion), 5) régime-switch (BTC vol percentile), 6) saisonnalité (skip). Faire 1,2,3,5 aujourd'hui.

**Contrarian** : "ton edge n'a qu'un régime de profondeur." 1) funding filtre (overfit min), 2) cross-sectional RS, 3) vol-targeting, 4) funding-divergence, 5) saisonnalité=REJETER. Exiger walk-forward.

**Outsider (reframe)** : arrête d'appeler le signal d'entrée "la stratégie" — sélection/exit/sizing/pairing sont les vrais leviers. 1) sélection AS edge (cross-sectional), 2) funding fade, 3) funding dispersion = régime-switch, 4) vol-targeting AS edge, 5) BTC-relative pairs (market-neutral). Mesurer Sharpe pas PF. Slippage sur alts fins = vrai ennemi.

**Expansionist** : 1) funding carry cross-sectional, 2) régime-switch toujours-actif, 3) cross-sectional RS, 4) vol-targeting, 5) stablecoin supply/netflow tilt (on-chain). Rang 2>1>4>3>5.
