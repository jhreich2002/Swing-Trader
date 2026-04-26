const BASE = import.meta.env.VITE_API_URL || ""

async function apiFetch(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  market: {
    regime:    () => apiFetch("/api/market/regime"),
    indices:   () => apiFetch("/api/market/indices"),
    synthesis: () => apiFetch("/api/market/synthesis"),
    news:      () => apiFetch("/api/market/news"),
  },
  recommendations: {
    list:   (week) => apiFetch(`/api/recommendations${week ? `?week=${week}` : ""}`),
    detail: (id)   => apiFetch(`/api/recommendations/${id}`),
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
