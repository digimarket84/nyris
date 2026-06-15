# Stratégie `live-meanrev-v2` — Mean-Reversion daily, univers élargi (100 alts USDT)

> **But de ce document** : permettre de **reproduire `live-meanrev-v2` à l'identique**.
> Tous les paramètres, l'univers exact, les coûts, l'infra et les résultats sont figés ici.
>
> **Statut** : déployée le **2026-06-10**, passée en **mode extinction** (plus de nouvelles
> entrées) le **2026-06-11** suite à la décision de recaler le sizing pour la V3. La logique
> ci-dessous décrit la version **ACTIVE** (telle qu'elle a tourné les 10-11/06).

---

## 1. Résumé exécutif
Mean-reversion **long-only daily** : on achète un alt **survendu** (RSI14 < 35) et on revend
au **rebond** (close > SMA10) ou après **20 jours** max. Appliquée à un univers **élargi de
~100 paires USDT liquides** (vs 13 sur la v1). Edge validé en backtest (PF 1.58 sur 30j,
généralise) **et** confirmé en live.

---

## 2. Logique de la stratégie (moteur — `nyris/strategy/meanrev_engine.py`)
Évaluée sur la **dernière bougie daily clôturée** (la bougie en cours est exclue).

**Entrée (LONG)** si **à plat** :
- `RSI(14) < 35` (survente modérée).
- Prix d'entrée = close de la bougie signal.

**Sortie** si **en position** (dans cet ordre de priorité) :
1. `bars_held >= 20` (jours) → `exit_max_hold` (anti bag-holding).
2. `close > SMA(10)` → `exit_recovered` (rebond confirmé).
3. sinon → on garde (`hold_in_position`).

**Warmup** : `max(rsi_period+1, exit_sma) + 2` bougies minimum.
Indicateurs : RSI de Wilder, SMA simple (`nyris/strategy/indicators.py`).

### Paramètres EXACTS (`MeanRevParams`, vérifiés sur le déploiement)
| Paramètre | Valeur |
|---|---|
| `timeframe` | `1d` |
| `rsi_period` | `14` |
| `rsi_buy` | `35.0` |
| `exit_sma` | `10` |
| `max_hold_days` | `20` |
| `per_position` | `Decimal("100")` (notional € par position) |
| `commission_rate` | `0.001` |
| `spread_rate` | `0.0005` |
| `slippage_rate` | `0.0005` |
| `funding_rate_daily` | `0` (long spot) |
| `run_id` | `live-meanrev-v2` |
| `params_key` | `meanrev-t1d_rsi14<35_sma10_h20` |
| `allow_entries` | `True` (version active ; `False` = extinction) |

### Modèle de coûts (`nyris/strategy/pattern_pnl.py`)
- Coût par côté = `commission + spread/2 + slippage` = `0.001 + 0.00025 + 0.0005` = **0.00175** (0,175 %).
- Aller-retour ≈ **0,35 %**. `entry_cost` et `exit_cost` proportionnels au notional.
- `pnl_net = (exit_value - notional) - entry_cost - exit_cost - funding_cost`.

---

## 3. ⚠️ Sizing — point CRITIQUE à comprendre pour reproduire/interpréter
- v2 ouvre **100 € par position, SANS plafond de capital** (1 position par alt survendu).
- Avec ~38-46 positions simultanées → **book notionnel de ~4 000-5 000 €**, PAS un compte de 50 €.
- **Conséquence** : les **€ absolus** des résultats (ci-dessous) sont « par unité de 100 €,
  illimité ». Les **% et le PF** sont, eux, valides indépendamment du capital.
- *(C'est précisément ce que la V3 corrigera : compte réel + K slots compoundés sans levier.)*

---

## 4. Univers (snapshot 2026-06-10, `nyris/strategy/meanrev_v2_universe.py`)
**100 paires USDT**, sélection = top par **volume 24h > 2 M$**, hors stablecoins / leveraged
tokens / or (PAXG, XAUT) / wrapped (WBTC) / symboles non-ASCII, avec **historique daily ≥ 40 j**.
Généré par `scripts/gen_universe_v2.py` (ré-exécutable pour rafraîchir le snapshot).

```
BTCUSDT ETHUSDT ZECUSDT SOLUSDT XRPUSDT WLDUSDT XLMUSDT NEARUSDT BNBUSDT DOGEUSDT
BABYUSDT TRXUSDT ADAUSDT ALLOUSDT SUIUSDT ENAUSDT HOMEUSDT PEPEUSDT TONUSDT TAOUSDT
STGUSDT SAHARAUSDT CHZUSDT KATUSDT LINKUSDT STRAXUSDT LTCUSDT AVAXUSDT SENTUSDT UUSDT
ONDOUSDT BCHUSDT INJUSDT HAEDALUSDT WLFIUSDT UTKUSDT FETUSDT CHIPUSDT OPNUSDT PENGUUSDT
ASTERUSDT AAVEUSDT HOLOUSDT TRUMPUSDT MOVEUSDT HMSTRUSDT IOUSDT FILUSDT HBARUSDT UNIUSDT
DASHUSDT PUMPUSDT IDUSDT SPKUSDT ARBUSDT RENDERUSDT DEXEUSDT JSTUSDT DOTUSDT BIOUSDT
EPICUSDT JTOUSDT ICPUSDT MORPHOUSDT APTUSDT ZBTUSDT ALTUSDT FFUSDT LUNCUSDT ZROUSDT
XPLUSDT ATOMUSDT VIRTUALUSDT CRVUSDT MANTRAUSDT ZKUSDT HIVEUSDT OSMOUSDT TIAUSDT WALUSDT
PORTALUSDT FORMUSDT AVNTUSDT HEIUSDT MEGAUSDT POLUSDT SUSDT RUNEUSDT LRCUSDT SHIBUSDT
ARUSDT OPUSDT ZAMAUSDT OPENUSDT ORDIUSDT PARTIUSDT SEIUSDT NEIROUSDT CAKEUSDT PENDLEUSDT
```
Symbole = paire USDT propre (ex. `BTCUSDT`) → **aucune collision** avec les actifs base
existants (BTC=BTCEUR reste intact). Chaque paire est upsertée comme `Asset`
(`symbol=BTCUSDT, binance_symbol=BTCUSDT, quote=USDT`) par `scripts/seed_universe_v2.py`.

---

## 5. Infrastructure
| Élément | Valeur |
|---|---|
| Stockage trades | table `pattern_trades`, `run_id=live-meanrev-v2`, `pattern="meanrev"`, `side="long"` |
| stop/TP | `None` → le `pattern_monitor` IGNORE ces positions (sorties gérées par le runner) |
| Runner | `python -m nyris.strategy.meanrev_v2_runner` (réutilise `run_cycle` de `meanrev_runner`) |
| Lock | `/srv/nyris/meanrev-v2-runner.lock` (fcntl) |
| Cron | `nyris-meanrev-v2-runner.timer` — **00:15 UTC** quotidien (après v1 00:10, trend 00:05) |
| Service | `nyris-meanrev-v2-runner.service` (oneshot, User=deploy) |

### Fichiers (commités sur GitHub `digimarket84/nyris`)
- `nyris/strategy/meanrev_models.py` — `MeanRevParams` (+ flag `allow_entries`)
- `nyris/strategy/meanrev_engine.py` — `evaluate_meanrev` (logique pure)
- `nyris/strategy/meanrev_runner.py` — runner partagé v1/v2 (+ garde-fou bougie périmée)
- `nyris/strategy/meanrev_v2_runner.py` — `MR_V2 = MeanRevParams(universe=PAIRS, run_id="live-meanrev-v2")`
- `nyris/strategy/meanrev_v2_universe.py` — les 100 paires
- `scripts/seed_universe_v2.py` — seed/re-seed des 100 actifs (à relancer après chaque pytest)
- `scripts/gen_universe_v2.py` — régénère le snapshot d'univers
- `scripts/bt_universe100.py` — backtest de validation
- `nyris-meanrev-v2-runner.service` / `.timer`

### Garde-fou « bougie fraîche » (anti-orphelin, `meanrev_runner.process_asset`)
Si la dernière bougie daily a `> 3 jours` (`STALE_MS`), on **skip** (`skip_stale_data`) :
évite d'ouvrir sur un prix périmé (token gelé/délisté) et les positions orphelines.

---

## 6. Validation
### Backtest (`scripts/bt_universe100.py`, ~150j daily, sizing 100 €/trade, net de frais)
| Fenêtre | Trades | Win | Net | PF |
|---|---|---|---|---|
| 30j | 36 | 64 % | +130 € | **1.58** |
| 60j | 55 | 62 % | +164 € | 1.60 |
| 90j | 101 | 61 % | +159 € | 1.36 |

Edge antérieurement validé OOS sur les alts (IS/OOS, plateau de paramètres robuste,
résistant aux coûts) — voir `scripts/README.md` (journal de recherche).

### Live (déploiement 10/06 → wind-down, hors trade orphelin `exit_orphan_stale`)
| Métrique | Valeur |
|---|---|
| Trades clôturés | **46** |
| Win rate | **93 %** |
| Net réalisé | **+336,79 €** *(base 100 €/position)* |
| Profit Factor | **89,40** |
| Durée médiane | ~48-72 h |
| Meilleur / Pire | +60,88 € (STRAX +61 %) / −2,97 € |

⚠️ **Caveats d'interprétation (honnêteté)** :
- **Régime favorable** : ce cohorte unique est tombée sur un **rebond de marché** en V — idéal
  pour « acheter le creux ». Le 93 %/PF 89 **n'est PAS annualisable** ; c'est *une* fenêtre chanceuse.
- **Sizing 100 €/position illimité** → les € sont sur ~5 000 € de notional, pas 50 €.
- **Biais de sortie** : sortie `close>SMA10` → une position qui rebondit ferme en profit par
  construction ; les gagnants sortent vite (~2j), les rares perdants vont au cap 20j.
- **Slippage** : sur les noms à 2-5 M$/j, les fills réels seraient pires que l'hypothèse 0,4 %.

---

## 7. Reproduire à l'identique
1. Code : `git checkout` du repo `digimarket84/nyris` (les fichiers listés §5 contiennent tout).
2. Univers : soit utiliser `meanrev_v2_universe.py` tel quel (snapshot 10/06), soit
   `PYTHONPATH=. python scripts/gen_universe_v2.py` pour régénérer (l'univers changera selon
   les volumes du jour).
3. Seed des actifs : `PYTHONPATH=. python scripts/seed_universe_v2.py`.
4. Installer le timer : copier `nyris-meanrev-v2-runner.{service,timer}` dans
   `/etc/systemd/system/`, `systemctl daemon-reload && systemctl enable --now nyris-meanrev-v2-runner.timer`.
5. (Entrées) S'assurer que `MR_V2.allow_entries=True` (le mode extinction le met à `False`).
6. Cycle manuel de test : `PYTHONPATH=. python -m nyris.strategy.meanrev_v2_runner`.
7. Suivi : page UI **Pattern** (filtre `run_id=live-meanrev-v2`) + `scripts/edge_monitor.py`.

> **Reproductibilité backtest** : `scripts/bt_universe100.py` rejoue le moteur exact sur
> l'univers — mêmes données = mêmes résultats (déterministe, indicateurs purs).

---
*Document figé le 2026-06-15. Source de vérité = le code commité sur GitHub.*
