# Journal de recherche — chasse à l'edge (backtests)

Tous les backtests sont en **lecture seule** (aucune écriture DB). Sizing fixe 100 €/trade,
net de frais (~0,2-0,4 % aller-retour). Données : klines Binance via `get_candles_paginated`.

**Principe directeur** : on ne déploie un runner que si l'edge est **prouvé out-of-sample**
(et de préférence robuste : plateau de paramètres, walk-forward / IS-OOS, sensibilité aux coûts,
généralisation cross-actifs, et il doit **battre le taux de base**, pas juste être positif).

## Résultats (ce qui est tranché)

| Stratégie | Script | Verdict | Détail |
|---|---|---|---|
| Trend-following daily (Donchian 100/50 long) | — (runner `live-trend-v1`) | ✅ edge **historique** (7 ans) mais **mort dans le marché actuel** | Bat B&H en risque-ajusté sur 7 ans ; perd sur 365/180/90j. Déployé mais dormant (attend un bull). |
| **Mean-reversion daily** (RSI14<35 long, alts volatils) | `bt_mr_*.py` | ✅ **EDGE VALIDÉ — déployé** (`live-meanrev-v1`) | +806€/7ans, +331€/365j ; **OOS +315€ PF1.65** ; plateau robuste ; frontière nette (buy40 s'effondre) ; résiste aux coûts. Majors exclus (MR négative). |
| Short trend filtré régime macro | `_bt_short_trend.py` (sur VPS /tmp) | ❌ pas d'edge | PF 0.45-0.96 toutes configs. Crypto = dérive haussière + rebonds violents. |
| Intraday/LLM (pattern Donchian, BB-RSI, ATR pullback) | runners `live-pattern/mistral/chatgpt/perplexity` | ❌ pas d'edge | 440 trades live, −36€, tous PF<1. « Mort par mille coupures » (frais > brut). pattern-v1 mis en pause. |
| **Analogues kNN 24h H1** (direction) | `bt_knn_analog.py` (v1), `bt_knn_v2.py` (v2 PCA+récence) | ❌ **pas d'edge (prouvé 2×)** | LIFT vs taux de base ≈ 0 ou négatif sur gros échantillons. Même avec PCA (dim réduite) + bibliothèque glissante (récence) + cible excédent. À H1, « forme 24h → futur » ne porte aucune info exploitable (quasi-efficience). |

## Leçons transversales
1. **Le marché a changé de régime** : trending (bull 2020-21, le trend gagnait) → choppy/range
   (2024-26, c'est la mean-reversion qui paie). Toujours backtester sur **fenêtres multiples**
   (tout / 365j / 180j / 90j / 30j), car *le crypto d'il y a 7 ans ≠ aujourd'hui*.
2. **La spécificité bat la généralité** : un edge précis et persistant (survente extrême → rebond)
   marche ; un pattern vague cherché par ML/kNN sur 14 features ne marche pas (déjà arbitré).
3. **Les frais tuent la haute fréquence sans edge** : multiplier les trades sans avantage = saigner.
4. **Petits échantillons mentent** : toujours exiger des n significatifs et un OOS propre.
5. **Battre 50% ne suffit pas** : il faut battre le **taux de base** (le marché a une dérive).

## Scripts
- `bt_battery.py` — batterie multi-stratégies daily (trend/momentum/MA-cross/MR) × fenêtres.
- `bt_meanrev.py` / `bt_mr_daily.py` / `bt_mr_validate.py` / `bt_mr_final.py` — développement + validation de l'edge mean-reversion.
- `bt_knn_analog.py` / `bt_knn_v2.py` — analogues kNN (archivés : pas d'edge).
- `analyse_strats.py` — analyse comparative live de tous les runners (réalisé + flottant).
- `sec_audit.sh` — audit sécurité VPS (lecture seule).
