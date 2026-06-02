// Helpers de formatage (affichage uniquement, ne modifie pas les valeurs API).
(function () {
  const eurFmt = new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const toNum = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

  // #3 - décimales contextuelles : on coupe les zéros inutiles selon l'ordre de grandeur
  function ctxMax(n) {
    const a = Math.abs(n);
    if (a >= 1000) return 2;
    if (a >= 1) return 4;
    if (a >= 0.01) return 6;
    return 8;
  }

  window.fmt = {
    // Montants (capital, PnL) : toujours 2 décimales
    eur(v) {
      const n = toNum(v);
      return n === null ? "—" : eurFmt.format(n);
    },
    // Prix unitaire en EUR : 2 décimales mini, plus si l'actif est "petit"
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
    // Nombre générique contextuel (quantités, prix bruts) — zéros inutiles coupés
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
    // --- PnL : valeur SIGNÉE (+/−). À réserver aux gains/pertes, jamais aux prix bruts. ---
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
    dt(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      return isNaN(d.getTime()) ? "—" : d.toLocaleString();
    },
    pnlClass(v) {
      const n = toNum(v);
      if (n === null) return "text-slate-500";
      if (n > 0) return "text-emerald-600";
      if (n < 0) return "text-red-600";
      return "text-slate-600";
    },
  };
})();
