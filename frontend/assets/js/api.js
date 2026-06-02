// Client API Nyris (same-origin). Lève ApiError sur réponse non-2xx.
(function () {
  class ApiError extends Error {
    constructor(status, detail) {
      super(detail || `HTTP ${status}`);
      this.status = status;
      this.detail = detail;
    }
  }

  function qs(params) {
    const u = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") u.append(k, v);
    });
    const s = u.toString();
    return s ? `?${s}` : "";
  }

  async function request(method, url, body) {
    const opts = { method, headers: {} };
    // Un seul endroit pour ajouter un header Authorization plus tard.
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw new ApiError(0, "Réseau / API injoignable");
    }
    const text = await resp.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }
    if (!resp.ok) {
      let detail = data && data.detail ? data.detail : data;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => d.msg || JSON.stringify(d)).join(" ; ");
      }
      throw new ApiError(resp.status, detail || `Erreur ${resp.status}`);
    }
    return data;
  }

  window.api = {
    ApiError,
    getHealth: () => request("GET", "/health"),
    getAssets: (params) => request("GET", "/api/v1/assets" + qs(params)),
    getMarketPrices: () => request("GET", "/api/v1/market/prices"),
    getMarketPrice: (assetId) => request("GET", "/api/v1/market/price" + qs({ asset_id: assetId })),
    postMarketSync: () => request("POST", "/api/v1/market/sync"),
    getPortfolioSummary: (params) => request("GET", "/api/v1/portfolio/summary" + qs(params)),
    getStrategyDecisions: (params) => request("GET", "/api/v1/strategy/decisions" + qs(params)),
    getTradesHistory: (params) => request("GET", "/api/v1/trades/history" + qs(params)),
    createTrade: (body) => request("POST", "/api/v1/trades", body),
    closeTrade: (id, body) => request("POST", `/api/v1/trades/${id}/close`, body),
    cancelTrade: (id) => request("POST", `/api/v1/trades/${id}/cancel`),
  };
})();
