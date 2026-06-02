// Helpers de formatage (affichage uniquement, ne modifie pas les valeurs API).
//
// ===================================================================
//  CONVENTION UI GLOBALE — couleur & signe des valeurs de performance
// ===================================================================
//  Toute valeur de GAIN / PERTE / PERFORMANCE (PnL €, PnL %, R, ...) :
//    - positive  -> vert  (text-emerald-600)  + signe "+"
//    - négative  -> rouge (text-red-600)       + signe "-"
//    - zéro/null -> gris/neutre (text-slate-500/600), sans signe
//  RÈGLES :
//    - NE PAS colorer les prix bruts sans contexte (close, EMA, ATR,
//      entry/stop/TP, capital investi, valeur de sortie, exposition...).
//    - Toujours utiliser ces helpers (pas de style couleur en dur dans les pages).
//  USAGE :
//    :class="fmt.pnlClass(v)"   + x-text="fmt.eurSigned(v)"   // montants PnL €
//    :class="fmt.pnlClass(v)"   + x-text="fmt.pctSigned(v)"   // PnL en %
//    :class="fmt.pnlClass(v)"   + x-text="fmt.numSigned(v)"   // métrique signée (R, ...)
// ===================================================================
(function () {
  const eurFmt = new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const toNum = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

  // décimales contextuelles : on coupe les zéros inutiles selon l'ordre de grandeur
  function ctxMax(n) {
    const a = Math.abs(n);
    if (a >= 1000) return 2;
    if (a >= 1) return 4;
    if (a >= 0.01) return 6;
    return 8;
  }

  window.fmt = {
    // --- Montants neutres (capital, valeurs brutes) : 2 décimales, PAS de signe/couleur ---
    eur(v) {
      const n = toNum(v);
      return n === null ? "—" : eurFmt.format(n);
    },
    // --- Prix unitaire en EUR (brut, neutre) ---
    priceEur(v) {
      const n = toNum(v);
      if (n === null) return "—";
      return new Intl.NumberFormat("fr-FR", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 2,
        maximumFractionDigits: Math.max(2, ctxMax(n)),
      }).format(n);
    },
    // --- Nombre générique contextuel (quantités, prix bruts, neutre) ---
    price(v) {
      const n = toNum(v);
      if (n === null) return "—";
      return new Intl.NumberFormat("fr-FR", {
        minimumFractionDigits: 0,
        maximumFractionDigits: ctxMax(n),
      }).format(n);
    },
    pct(v) {
      const n = toNum(v);
      return n === null ? "—" : `${n.toFixed(2)} %`;
    },

    // --- PERFORMANCE : valeurs SIGNÉES (+/−). À coupler avec pnlClass(). ---
    eurSigned(v) {
      const n = toNum(v);
      if (n === null) return "—";
      const s = eurFmt.format(n); // gère déjà le signe négatif et la devise
      return n > 0 ? `+${s}` : s; // positif -> "+", zéro -> neutre
    },
    pctSigned(v) {
      const n = toNum(v);
      if (n === null) return "—";
      const sign = n > 0 ? "+" : ""; // négatif déjà signé par toFixed
      return `${sign}${n.toFixed(2)} %`;
    },
    numSigned(v, digits = 2) {
      const n = toNum(v);
      if (n === null) return "—";
      const sign = n > 0 ? "+" : "";
      return `${sign}${n.toFixed(digits)}`;
    },

    dt(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      return isNaN(d.getTime()) ? "—" : d.toLocaleString();
    },

    // --- Classe couleur unique pour TOUTE valeur de performance ---
    pnlClass(v) {
      const n = toNum(v);
      if (n === null) return "text-slate-500";
      if (n > 0) return "text-emerald-600";
      if (n < 0) return "text-red-600";
      return "text-slate-600";
    },
  };
})();
