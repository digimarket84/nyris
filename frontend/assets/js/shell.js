// Shell commun : top-nav, pastille état API/DB, bannières d'erreur/info.
(function () {
  const PAGES = [
    { href: "index.html", label: "Dashboard" },
    { href: "market.html", label: "Marché" },
    { href: "new-trade.html", label: "Nouveau trade" },
    { href: "trades.html", label: "Historique" },
    { href: "decisions.html", label: "Décisions" },
    { href: "short-trades.html", label: "Short" },
    { href: "pattern-trades.html", label: "Pattern" },
    { href: "mistral-long.html", label: "Mistral L-O" },
  ];
  const current = location.pathname.split("/").pop() || "index.html";
  let bannerTimer = null;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function renderHeader() {
    const el = document.getElementById("shell-header");
    if (!el) return;
    const links = PAGES.map((p) => {
      const active = p.href === current || (current === "" && p.href === "index.html");
      const cls = active
        ? "px-3 py-1.5 rounded-md text-sm font-medium bg-slate-900 text-white"
        : "px-3 py-1.5 rounded-md text-sm font-medium text-slate-600 hover:bg-slate-200";
      return `<a href="${p.href}" class="${cls}">${p.label}</a>`;
    }).join("");
    el.innerHTML = `
      <header class="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div class="max-w-6xl mx-auto px-4 py-2 flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-baseline gap-2">
            <span class="font-semibold text-slate-900">Nyris</span>
            <span class="text-xs text-slate-400">paper trading</span>
          </div>
          <nav class="flex items-center gap-1 flex-wrap">${links}</nav>
          <div id="api-status" class="text-xs text-slate-500 flex items-center gap-1.5">
            <span class="inline-block w-2 h-2 rounded-full bg-slate-300"></span><span>…</span>
          </div>
        </div>
      </header>`;
  }

  async function refreshHealth() {
    const box = document.getElementById("api-status");
    if (!box) return;
    try {
      const h = await window.api.getHealth();
      const ok = h.status === "ok" && h.database === "ok";
      const color = ok ? "bg-emerald-500" : "bg-red-500";
      box.innerHTML = `<span class="inline-block w-2 h-2 rounded-full ${color}"></span><span>API ${esc(h.status)} · DB ${esc(h.database)}</span>`;
    } catch (e) {
      box.innerHTML = `<span class="inline-block w-2 h-2 rounded-full bg-red-500"></span><span>API injoignable</span>`;
    }
  }

  function clearBanner() {
    if (bannerTimer) {
      clearTimeout(bannerTimer);
      bannerTimer = null;
    }
    const el = document.getElementById("error-banner");
    if (el) el.innerHTML = "";
  }

  // #2 - bannière fermable ; les infos (succès) s'effacent seules après 4 s
  function banner(kind, msg) {
    const el = document.getElementById("error-banner");
    if (!el) return;
    if (bannerTimer) {
      clearTimeout(bannerTimer);
      bannerTimer = null;
    }
    const styles =
      kind === "error"
        ? "border-red-200 bg-red-50 text-red-700"
        : "border-emerald-200 bg-emerald-50 text-emerald-700";
    el.innerHTML = `<div class="mb-4 rounded-md border ${styles} px-4 py-3 text-sm flex items-start justify-between gap-3">
        <span>${esc(msg)}</span>
        <button type="button" aria-label="Fermer" onclick="window.shell.clearError()"
          class="leading-none text-base opacity-60 hover:opacity-100">&times;</button>
      </div>`;
    if (kind === "info") {
      bannerTimer = setTimeout(clearBanner, 4000);
    }
  }

  window.shell = {
    showError: (msg) => banner("error", msg),
    showInfo: (msg) => banner("info", msg),
    clearError: clearBanner,
  };

  document.addEventListener("DOMContentLoaded", () => {
    renderHeader();
    refreshHealth();
  });
})();
