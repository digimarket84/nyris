// Helpers de formatage (affichage uniquement, ne modifie pas les valeurs API).
(function () {
  const eur = new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const num = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 8 });

  const toNum = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

  window.fmt = {
    eur(v) {
      const n = toNum(v);
      return n === null ? "—" : eur.format(n);
    },
    pct(v) {
      const n = toNum(v);
      return n === null ? "—" : `${n.toFixed(2)} %`;
    },
    price(v) {
      const n = toNum(v);
      return n === null ? "—" : num.format(n);
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
