# Conventions UI — Dashboard Nyris

## Couleur & signe des valeurs de performance (RÈGLE GLOBALE)

Toute valeur représentant un **gain / perte / performance** (PnL €, PnL %, R, ratio
de performance, rendement…) doit suivre cette règle, **partout** dans le dashboard :

| Cas | Couleur | Signe |
|---|---|---|
| Positif (gain) | **vert** (`text-emerald-600`) | `+` |
| Négatif (perte) | **rouge** (`text-red-600`) | `-` |
| Zéro / neutre / `null` | **gris** (`text-slate-500/600`) | aucun |

### À NE PAS colorer
Les **prix bruts sans contexte de gain/perte** restent neutres :
`close`, `entry`, `stop`, `take_profit`, `EMA`, `ATR`, capital investi,
valeur de sortie, exposition, quantités, frais…

### Comment l'appliquer (helpers communs — source unique : `assets/js/format.js`)
Toujours coupler **la couleur** (`fmt.pnlClass`) avec **la valeur signée** :

```html
<!-- montant PnL en euros -->
<span :class="fmt.pnlClass(v)" x-text="fmt.eurSigned(v)"></span>

<!-- PnL en pourcentage -->
<span :class="fmt.pnlClass(v)" x-text="fmt.pctSigned(v)"></span>

<!-- métrique de performance signée (ex. R) -->
<span :class="fmt.pnlClass(v)" x-text="fmt.numSigned(v)"></span>
```

Interdit : couleur en dur (`text-green-600`…) dans une page. Toujours passer par `fmt.pnlClass`.

## Où la convention s'applique
- **Dashboard** : PnL net réalisé, PnL %, PnL par actif, meilleur/pire actif. ✅
- **Historique** : colonnes PnL net & PnL %. ✅
- **Nouveau trade** : dès qu'une **estimation de résultat** (gain/perte) est affichée.
- **Décisions** : dès qu'une **métrique de performance** y est ajoutée.

> Checklist en ajoutant une valeur perf : est-ce un gain/perte ? → `fmt.pnlClass` + `fmt.*Signed`.
> Est-ce un prix/quantité brut ? → format neutre (`fmt.eur` / `fmt.priceEur` / `fmt.price`), sans couleur.
