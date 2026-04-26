import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { createChart, ColorType, HistogramSeries } from "lightweight-charts"
import { api } from "../api/api"
import CandlestickChart from "../components/charts/CandlestickChart"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(v, { pct = false, x = false, decimals = 2 } = {}) {
  if (v == null) return "—"
  const n = parseFloat(v)
  if (isNaN(n)) return "—"
  if (pct) return `${(n * 100).toFixed(1)}%`
  if (x)   return `${n.toFixed(1)}x`
  return n.toFixed(decimals)
}

function fmtLarge(v) {
  if (v == null) return "—"
  const n = parseFloat(v)
  if (isNaN(n)) return "—"
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`
  return `$${n.toLocaleString()}`
}

function growthColor(v) {
  if (v == null) return "text-gray-400"
  return parseFloat(v) >= 0 ? "text-green-400" : "text-red-400"
}

function Spinner({ size = "h-5 w-5" }) {
  return (
    <svg className={`animate-spin ${size}`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

// Compact stat chip
function Stat({ label, value, valueClass = "text-white" }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 py-2 rounded-lg bg-surface">
      <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wide truncate">{label}</span>
      <span className={`text-sm font-semibold ${valueClass}`}>{value}</span>
    </div>
  )
}

// Ratio row — compact, used inside the ratio panels
function RatioRow({ label, value, valueClass = "text-white" }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-xs font-semibold ${valueClass}`}>{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 52-week range bar
// ---------------------------------------------------------------------------
function RangeBar({ low, high, current }) {
  if (low == null || high == null || current == null) return null
  const pct = Math.min(Math.max(((current - low) / (high - low)) * 100, 0), 100)
  return (
    <div className="mt-2">
      <div className="flex justify-between text-[10px] text-gray-500 mb-1">
        <span>${parseFloat(low).toFixed(2)}</span>
        <span className="text-gray-600">52-wk range</span>
        <span>${parseFloat(high).toFixed(2)}</span>
      </div>
      <div className="relative h-1 bg-border rounded-full">
        <div className="absolute inset-0 bg-gradient-to-r from-red-500 via-yellow-400 to-green-500 rounded-full" />
        <div
          className="absolute top-1/2 -translate-y-1/2 h-2.5 w-2.5 bg-white border-2 border-accent rounded-full shadow"
          style={{ left: `calc(${pct}% - 5px)` }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Quarterly histogram chart using lightweight-charts
// ---------------------------------------------------------------------------
function QuarterlyChart({ data, positiveColor = "#6366f1", negativeColor = "#f87171", height = 160 }) {
  const containerRef = useRef(null)
  const chartRef     = useRef(null)
  const seriesRef    = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#1a1d27" },
        textColor:  "#6b7280",
      },
      grid: {
        vertLines: { color: "#2a2d3e" },
        horzLines: { color: "#2a2d3e" },
      },
      crosshair:       { mode: 1 },
      rightPriceScale: { borderColor: "#2a2d3e", scaleMargins: { top: 0.15, bottom: 0.1 } },
      timeScale:       { borderColor: "#2a2d3e", timeVisible: false, fixLeftEdge: true, fixRightEdge: true },
      width:  containerRef.current.clientWidth,
      height,
      handleScroll: false,
      handleScale:  false,
    })
    chartRef.current = chart
    seriesRef.current = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      base: 0,
    })

    const ro = new ResizeObserver(() => {
      if (containerRef.current)
        chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove() }
  }, [height])

  useEffect(() => {
    if (!seriesRef.current || !data?.length) return
    const formatted = [...data]
      .sort((a, b) => a.time.localeCompare(b.time))
      .map(d => ({
        time:  d.time,
        value: d.value,
        color: d.value >= 0 ? positiveColor : negativeColor,
      }))
    seriesRef.current.setData(formatted)
    chartRef.current?.timeScale().fitContent()
  }, [data, positiveColor, negativeColor])

  return <div ref={containerRef} className="w-full" />
}

// Generate approximate quarter-end dates going back N quarters from today
function quarterDates(count) {
  const dates = []
  const now   = new Date()
  // Snap to previous quarter end
  const month = now.getMonth()
  const qEnd  = month < 3 ? 0 : month < 6 ? 3 : month < 9 ? 6 : 9
  let year    = now.getFullYear()
  let q       = qEnd

  for (let i = 0; i < count; i++) {
    const lastDay = new Date(year, q + 3, 0)
    const mm = String(lastDay.getMonth() + 1).padStart(2, "0")
    const dd = String(lastDay.getDate()).padStart(2, "0")
    dates.unshift(`${year}-${mm}-${dd}`)
    q -= 3
    if (q < 0) { q += 12; year-- }
  }
  return dates
}

// ---------------------------------------------------------------------------
// Cramer checklist
// ---------------------------------------------------------------------------
const STATUS_CFG = {
  pass:    { icon: "✓", color: "text-green-400",  bg: "bg-green-900/20",  border: "border-green-900/60"  },
  fail:    { icon: "✗", color: "text-red-400",    bg: "bg-red-900/20",    border: "border-red-900/60"    },
  partial: { icon: "~", color: "text-yellow-400", bg: "bg-yellow-900/20", border: "border-yellow-800/60" },
  unknown: { icon: "?", color: "text-gray-500",   bg: "bg-white/5",       border: "border-white/10"      },
}
const CAT_ORDER  = ["fundamentals", "quality", "risk"]
const CAT_LABELS = { fundamentals: "Fundamentals", quality: "Business Quality", risk: "Risk Flags" }

function CramerChecklist({ checks }) {
  if (!checks?.length) return null
  const passed = checks.filter(c => c.status === "pass").length
  const total  = checks.length
  const pct    = Math.round((passed / total) * 100)
  const barColor   = pct >= 75 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500"
  const scoreColor = pct >= 75 ? "text-green-400" : pct >= 50 ? "text-yellow-400" : "text-red-400"
  const grouped = CAT_ORDER.map(cat => ({ cat, items: checks.filter(c => c.category === cat) })).filter(g => g.items.length)

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">Cramer Pre-Buy Checklist</h3>
          <p className="text-[10px] text-gray-600 mt-0.5">"Getting Back to Even" framework</p>
        </div>
        <span className={`text-xl font-bold ${scoreColor}`}>{passed}<span className="text-gray-600 text-sm">/{total}</span></span>
      </div>
      <div className="h-1 rounded-full bg-border mb-3 overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="space-y-3">
        {grouped.map(({ cat, items }) => (
          <div key={cat}>
            <p className="text-[9px] font-semibold text-gray-600 uppercase tracking-wider mb-1.5">{CAT_LABELS[cat]}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
              {items.map(check => {
                const cfg = STATUS_CFG[check.status] || STATUS_CFG.unknown
                return (
                  <div key={check.id} className={`flex gap-2 px-2.5 py-2 rounded-lg border ${cfg.bg} ${cfg.border}`}>
                    <span className={`text-xs font-bold flex-shrink-0 ${cfg.color}`}>{cfg.icon}</span>
                    <div className="min-w-0">
                      <p className={`text-[11px] font-semibold leading-tight ${cfg.color}`}>{check.label}</p>
                      <p className="text-[10px] text-gray-500 leading-snug mt-0.5">{check.rationale}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// AI panel
// ---------------------------------------------------------------------------
function AiPanel({ title, content, accent, icon }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = content?.length > 500
  return (
    <div className={`rounded-xl border ${accent.border} ${accent.bg} p-4`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={accent.icon}>{icon}</span>
        <h3 className={`text-[10px] font-bold uppercase tracking-widest ${accent.title}`}>{title}</h3>
      </div>
      {content ? (
        <>
          <p className={`text-xs text-gray-300 leading-relaxed whitespace-pre-wrap ${isLong && !expanded ? "line-clamp-5" : ""}`}>{content}</p>
          {isLong && (
            <button onClick={() => setExpanded(e => !e)} className={`mt-1.5 text-[11px] font-medium ${accent.title} hover:opacity-80`}>
              {expanded ? "Show less" : "Read more"}
            </button>
          )}
        </>
      ) : (
        <p className="text-xs text-gray-600 italic">Analysis unavailable.</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// News card
// ---------------------------------------------------------------------------
function NewsCard({ article }) {
  const dt = article.datetime
    ? (isNaN(Number(article.datetime))
        ? new Date(article.datetime)
        : new Date(Number(article.datetime) * 1000)
      ).toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : ""
  return (
    <a href={article.url} target="_blank" rel="noopener noreferrer"
       className="flex gap-2.5 p-2.5 rounded-lg hover:bg-white/5 transition-colors group">
      {article.image && (
        <img src={article.image} alt="" className="h-12 w-16 rounded object-cover flex-shrink-0 opacity-70 group-hover:opacity-100" />
      )}
      <div className="min-w-0">
        <p className="text-xs text-gray-200 font-medium line-clamp-2 group-hover:text-white leading-snug">{article.headline}</p>
        <p className="text-[10px] text-gray-600 mt-0.5">{article.source}{dt ? ` · ${dt}` : ""}</p>
      </div>
    </a>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
const PERIODS = [
  { label: "1M", days: 30  },
  { label: "3M", days: 90  },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
]

export default function WatchlistDetail() {
  const { ticker }                  = useParams()
  const [digest, setDigest]         = useState(null)
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [chartBars, setChartBars]   = useState([])
  const [chartDays, setChartDays]   = useState(180)
  const pollRef                     = useRef(null)

  function load() {
    api.watchlist.digest(ticker)
      .then(d => {
        setDigest(d)
        setLoading(false)
        if (d.digest_status === "running" || d.digest_status === "pending") startPolling()
        else stopPolling()
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }

  function startPolling() {
    if (pollRef.current) return
    pollRef.current = setInterval(() => {
      api.watchlist.digest(ticker).then(d => {
        setDigest(d)
        if (d.digest_status !== "running" && d.digest_status !== "pending") stopPolling()
      }).catch(console.error)
    }, 4000)
  }

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  useEffect(() => { load(); return () => stopPolling() }, [ticker])

  useEffect(() => {
    api.stock.chart(ticker, "candle", chartDays)
      .then(d => setChartBars(d.bars || []))
      .catch(() => setChartBars([]))
  }, [ticker, chartDays])

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await api.watchlist.refresh(ticker)
      setDigest(d => ({ ...d, digest_status: "running" }))
      startPolling()
    } catch (e) { console.error(e) }
    finally { setRefreshing(false) }
  }

  if (loading) return (
    <div className="flex items-center justify-center py-32 gap-3 text-gray-500">
      <Spinner /><span>Loading digest…</span>
    </div>
  )
  if (error) return <div className="text-center py-32 text-red-400">{error}</div>

  const isRunning = digest?.digest_status === "running" || digest?.digest_status === "pending"
  if (isRunning) return (
    <div className="space-y-4">
      <Link to="/watchlist" className="text-gray-500 hover:text-white text-xs">← Watchlist</Link>
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-white">{ticker}</h1>
        <span className="text-xs text-blue-300 border border-blue-800 bg-blue-900/30 px-2.5 py-1 rounded-full flex items-center gap-1.5">
          <Spinner size="h-3.5 w-3.5" /> Building digest…
        </span>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {[...Array(6)].map((_, i) => <div key={i} className="animate-pulse bg-card border border-border rounded-xl h-28" />)}
      </div>
      <p className="text-center text-sm text-gray-600">Fetching data + running AI analysis (~60s)</p>
    </div>
  )

  const r = digest?.ratios || {}

  // EPS chart data — use period dates from eps_quarters
  const epsData = (digest?.eps_quarters || [])
    .filter(q => q.period && q.epsActual != null)
    .map(q => ({ time: q.period.slice(0, 10), value: q.epsActual }))
    .slice(0, 8)

  // Revenue chart data — generate approximate quarter-end dates
  const revRaw  = (digest?.revenue_quarters || []).slice(0, 8)
  const revDates = quarterDates(revRaw.length)
  const revData  = revRaw.map((v, i) => ({ time: revDates[i], value: v / 1e9 }))

  const upside = digest.analyst_target && digest.current_price
    ? ((parseFloat(digest.analyst_target) - parseFloat(digest.current_price)) / parseFloat(digest.current_price)) * 100
    : null

  const consensusCls = {
    buy:  "text-green-400 border-green-800 bg-green-900/20",
    hold: "text-yellow-400 border-yellow-800 bg-yellow-900/20",
    sell: "text-red-400 border-red-800 bg-red-900/20",
  }[digest?.analyst_consensus] || "text-gray-400 border-gray-700 bg-white/5"

  return (
    <div className="space-y-4">

      {/* Back */}
      <Link to="/watchlist" className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-white transition-colors">
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Watchlist
      </Link>

      {/* ── STOCK CHART (full width) ─────────────────────────────────────────── */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-baseline gap-2">
            <h1 className="text-xl font-bold text-white">{digest.ticker}</h1>
            <span className="text-sm text-gray-500">{digest.name}</span>
            {digest.sector && <span className="text-xs text-gray-600">· {digest.sector}</span>}
          </div>
          <div className="flex gap-1">
            {PERIODS.map(({ label, days }) => (
              <button key={label} onClick={() => setChartDays(days)}
                className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${chartDays === days ? "bg-accent text-white" : "text-gray-500 hover:text-white"}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        {chartBars.length > 0
          ? <CandlestickChart bars={chartBars} height={260} />
          : <div className="h-64 flex items-center justify-center text-gray-600 text-sm animate-pulse">Loading chart…</div>
        }
      </div>

      {/* ── KEY RATIOS | PROFITABILITY | STATS BOX ──────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Key Ratios */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">Valuation</h3>
          <RatioRow label="Market Cap"    value={fmtLarge(r.market_cap)} />
          <RatioRow label="P/E (Forward)" value={fmt(r.pe_forward, { x: true })} />
          <RatioRow label="P/E (Trailing)"value={fmt(r.pe_trailing, { x: true })} />
          <RatioRow label="P/S"           value={fmt(r.ps_ratio, { x: true })} />
          <RatioRow label="P/B"           value={fmt(r.pb_ratio, { x: true })} />
          <RatioRow label="EV/EBITDA"     value={fmt(r.ev_ebitda, { x: true })} />
          <RatioRow label="Beta"          value={fmt(r.beta)} />
          <RatioRow label="Dividend Yield"value={fmt(r.dividend_yield, { pct: true })} />
          <RatioRow label="Total Debt"    value={fmtLarge(r.total_debt)} />
          <RatioRow label="D/E Ratio"     value={fmt(r.debt_to_equity, { x: true })} />
          <RatioRow label="Current Ratio" value={fmt(r.current_ratio, { x: true })} />
        </div>

        {/* Profitability */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">Profitability & Growth</h3>
          <RatioRow label="Gross Margin"   value={fmt(r.gross_margin, { pct: true })} />
          <RatioRow label="Oper. Margin"   value={fmt(r.operating_margin, { pct: true })} />
          <RatioRow label="Net Margin"     value={fmt(r.net_margin, { pct: true })} />
          <RatioRow label="ROE"            value={fmt(r.roe, { pct: true })} />
          <RatioRow label="ROA"            value={fmt(r.roa, { pct: true })} />
          <RatioRow label="Free Cash Flow" value={fmtLarge(r.free_cashflow)} />
          <RatioRow label="Revenue Growth" value={fmt(r.revenue_growth, { pct: true })}
            valueClass={growthColor(r.revenue_growth)} />
          <RatioRow label="Earn. Growth"   value={fmt(r.earnings_growth, { pct: true })}
            valueClass={growthColor(r.earnings_growth)} />
          <RatioRow label="Enterprise Val" value={fmtLarge(r.enterprise_value)} />
        </div>

        {/* Stats box (pushed right, below chart) */}
        <div className="bg-card border border-border rounded-xl p-4 flex flex-col justify-between">
          <div className="space-y-3">
            {/* Price + consensus */}
            <div className="flex items-start justify-between">
              <div>
                <p className="text-3xl font-bold text-white">
                  {digest.current_price ? `$${parseFloat(digest.current_price).toFixed(2)}` : "—"}
                </p>
                {digest.analyst_consensus && (
                  <span className={`inline-block mt-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${consensusCls}`}>
                    {digest.analyst_consensus}
                  </span>
                )}
              </div>
            </div>

            {/* 52w range */}
            <RangeBar low={r.week52_low} high={r.week52_high} current={digest.current_price} />

            {/* Quick stats grid */}
            <div className="grid grid-cols-2 gap-1.5 pt-1">
              <Stat label="Analyst PT" value={digest.analyst_target ? `$${parseFloat(digest.analyst_target).toFixed(2)}` : "—"} />
              <Stat label="Upside"
                value={upside != null ? `${upside >= 0 ? "+" : ""}${upside.toFixed(1)}%` : "—"}
                valueClass={upside != null ? (upside >= 0 ? "text-green-400" : "text-red-400") : "text-gray-400"}
              />
              <Stat label="52W High" value={r.week52_high ? `$${parseFloat(r.week52_high).toFixed(2)}` : "—"} />
              <Stat label="52W Low"  value={r.week52_low  ? `$${parseFloat(r.week52_low).toFixed(2)}`  : "—"} />
            </div>

            {digest.earnings_date && (
              <p className="text-[10px] text-yellow-400 bg-yellow-900/20 border border-yellow-900/50 px-2 py-1.5 rounded">
                Next earnings: {digest.earnings_date}
              </p>
            )}
          </div>

          <button onClick={handleRefresh} disabled={refreshing}
            className="mt-4 flex items-center gap-1 text-[10px] text-gray-600 hover:text-gray-300 transition-colors disabled:opacity-40">
            <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {refreshing ? "Refreshing…" : "Refresh digest"}
          </button>
        </div>
      </div>

      {/* ── EPS + REVENUE CHARTS ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-3">
            EPS — Quarterly (most recent right)
          </h3>
          {epsData.length > 0
            ? <QuarterlyChart data={epsData} positiveColor="#6366f1" negativeColor="#f87171" height={160} />
            : <p className="text-xs text-gray-600 py-8 text-center">No EPS data available.</p>
          }
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Revenue — Quarterly $B (most recent right)
          </h3>
          {revData.length > 0
            ? <QuarterlyChart data={revData} positiveColor="#34d399" negativeColor="#f87171" height={160} />
            : <p className="text-xs text-gray-600 py-8 text-center">No revenue data available.</p>
          }
        </div>
      </div>

      {/* ── CRAMER CHECKLIST ─────────────────────────────────────────────────── */}
      {digest.cramer_checklist?.length > 0 && (
        <CramerChecklist checks={digest.cramer_checklist} />
      )}

      {/* ── BULL / BEAR ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AiPanel title="Bull Case — Long-Term Upside" content={digest.bull_case} icon="▲"
          accent={{ border: "border-green-900", bg: "bg-green-950/30", title: "text-green-400", icon: "text-green-500" }} />
        <AiPanel title="Bear Case — Risks & Downside" content={digest.bear_case} icon="▼"
          accent={{ border: "border-red-900", bg: "bg-red-950/20", title: "text-red-400", icon: "text-red-500" }} />
      </div>

      {/* ── NEWS ─────────────────────────────────────────────────────────────── */}
      {digest.news?.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">Recent News</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0.5">
            {digest.news.map((a, i) => <NewsCard key={i} article={a} />)}
          </div>
        </div>
      )}

      {/* Footer */}
      <p className="text-[10px] text-gray-700 text-center pb-3">
        Digest {digest.digested_at ? new Date(digest.digested_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "pending"}
        {" · "}yfinance + Finnhub · Google Gemini
      </p>
    </div>
  )
}
