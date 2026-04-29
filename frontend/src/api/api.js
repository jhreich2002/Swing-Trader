const BASE = import.meta.env.VITE_API_URL || ""

async function apiFetch(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

function jsonBody(method, body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }
}

export const api = {
  market: {
    regime:    () => apiFetch("/api/market/regime"),
    indices:   () => apiFetch("/api/market/indices"),
    synthesis: () => apiFetch("/api/market/synthesis"),
    news:      () => apiFetch("/api/market/news"),
  },
  recommendations: {
    list:         (week) => apiFetch(`/api/recommendations${week ? `?week=${week}` : ""}`),
    detail:       (id)   => apiFetch(`/api/recommendations/${id}`),
    hypothetical: ()     => apiFetch("/api/recommendations/hypothetical"),
  },
  stock: {
    chart:        (ticker, type = "candle", days = 90) =>
      apiFetch(`/api/stock/${ticker}/chart?type=${type}&days=${days}`),
    fundamentals: (ticker) => apiFetch(`/api/stock/${ticker}/fundamentals`),
    news:         (ticker) => apiFetch(`/api/stock/${ticker}/news`),
    competitors:  (ticker) => apiFetch(`/api/stock/${ticker}/competitors`),
  },
  portfolio: {
    performance: () => apiFetch("/api/portfolio/performance"),
    trades:      () => apiFetch("/api/portfolio/trades"),

    // Multi-portfolio scoped accessors. Use api.portfolio.scope("active"|"roth_ira"|"passive").
    scope: (ptype) => ({
      actual:    () => apiFetch(`/api/portfolio/${ptype}/actual`),
      holdings: {
        list:        ()       => apiFetch(`/api/portfolio/${ptype}/holdings`),
        setCash:     (amount) => apiFetch(`/api/portfolio/${ptype}/holdings/cash`, jsonBody("PUT", { amount })),
        upsertStock: (data)   => apiFetch(`/api/portfolio/${ptype}/holdings`, jsonBody("POST", data)),
        patchStock:  (id, data) => apiFetch(`/api/portfolio/${ptype}/holdings/${id}`, jsonBody("PATCH", data)),
        remove:      (id)     => apiFetch(`/api/portfolio/${ptype}/holdings/${id}`, { method: "DELETE" }),
      },
      recommendations: {
        latest:   () => apiFetch(`/api/portfolio/${ptype}/recommendations`),
        generate: () => apiFetch(`/api/portfolio/${ptype}/recommendations`, { method: "POST" }),
      },
    }),

    total:           () => apiFetch("/api/portfolio/total"),
    totalRecommendations: {
      latest:   () => apiFetch("/api/portfolio/total/recommendations"),
      generate: () => apiFetch("/api/portfolio/total/recommendations", { method: "POST" }),
    },

    // ----- legacy unscoped aliases (deprecated, still used by old components) -----
    actual:      () => apiFetch("/api/portfolio/active/actual"),
    holdings: {
      list:        ()       => apiFetch("/api/portfolio/active/holdings"),
      setCash:     (amount) => apiFetch("/api/portfolio/active/holdings/cash", jsonBody("PUT", { amount })),
      upsertStock: (data)   => apiFetch("/api/portfolio/active/holdings", jsonBody("POST", data)),
      remove:      (id)     => apiFetch(`/api/portfolio/active/holdings/${id}`, { method: "DELETE" }),
    },
  },
  scan: {
    run:    () => apiFetch("/api/scan/run", { method: "POST" }),
    status: () => apiFetch("/api/scan/status"),
  },
  watchlist: {
    list:    ()       => apiFetch("/api/watchlist"),
    add:     (ticker) => apiFetch(`/api/watchlist/${ticker}`, { method: "POST" }),
    remove:  (ticker) => apiFetch(`/api/watchlist/${ticker}`, { method: "DELETE" }),
    digest:  (ticker) => apiFetch(`/api/watchlist/${ticker}`),
    refresh: (ticker) => apiFetch(`/api/watchlist/${ticker}/refresh`, { method: "POST" }),
  },
}
