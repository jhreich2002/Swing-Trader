import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { api } from "../api/api"
import CandlestickChart from "../components/charts/CandlestickChart"
import RegimeBadge from "../components/market/RegimeBadge"
import NewsItem from "../components/market/NewsItem"
import CompetitorTable from "../components/recommendations/CompetitorTable"

function Card({ title, children, className = "" }) {
  return (
    <div className={`bg-card border border-border rounded-xl p-5 ${className}`}>
      {title && <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">{title}</h2>}
      {children}
    </div>
  )
}

function Skeleton({ className = "h-6" }) {
  return <div className={`animate-pulse bg-border rounded ${className}`} />
}

function fmt(v) {
  if (v == null) return "—"
  return `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(v) {
  if (v == null) return "—"
  return `${Number(v).toFixed(2)}%`
}

function fmtCap(v) {
  if (!v) return "—"
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(0)}B`
  return `$${(v / 1e6).toFixed(0)}M`
}

const SIGNAL_LABELS = {
  rsi: "RSI Recovery", ma: "MA Crossover", macd: "MACD",
  volume: "Volume Surge", support: "Support Bounce",
  rs: "Relative Strength", bollinger: "Bollinger Breakout",
}

export default function TradeDetail() {
  const { id } = useParams()
  const [rec,          setRec]          = useState(null)
  const [chart,        setChart]        = useState([])
  const [fundamentals, setFundamentals] = useState(null)
  const [news,         setNews]         = useState([])
  const [competitors,  setCompetitors]  = useState([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState(null)

  useEffect(() => {
    setLoading(true)
    api.recommendations.detail(id)
      .then(r => {
        setRec(r)
        // Fire remaining calls now that we have the ticker
        return Promise.allSettled([
          api.stock.chart(r.ticker, "candle", 90),
          api.stock.fundamentals(r.ticker),
          api.stock.news(r.ticker),
          api.stock.competitors(r.ticker),
        ])
      })
      .then(([chartR, fundR, newsR, compR]) => {
        if (chartR.status === "fulfilled") setChart(chartR.value.bars || [])
        if (fundR.status  === "fulfilled") setFundamentals(fundR.value)
        if (newsR.status  === "fulfilled") setNews(newsR.value.articles || [])
        if (compR.status  === "fulfilled") setCompetitors(compR.value.competitors || [])
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (error) return (
    <div className="text-center py-20">
      <p className="text-red-400 mb-4">{error}</p>
      <Link to="/trades" className="text-accent hover:underline text-sm">← Back to trades</Link>
    </div>
  )

  if (loading || !rec) return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-80 w-full rounded-xl" />
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    </div>
  )

  const positionValue = 10000
  const shares = rec.entry_price ? (positionValue / rec.entry_price).toFixed(2) : "—"
  const stopDistPct = rec.stop_distance_pct ? `${rec.stop_distance_pct.toFixed(2)}%` : "—"
  const firedSignals = rec.signals_fired || []
  const techBreak = rec.technical_breakdown || {}

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link to="/trades" className="text-accent hover:underline text-sm inline-flex items-center gap-1">
        ← Weekly Trades
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">{rec.ticker}</h1>
          <p className="text-gray-400">{rec.name}</p>
          {rec.sector && <p className="text-xs text-gray-600 mt-0.5">{rec.sector}</p>}
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-white">{fmt(rec.current_price)}</p>
          <RegimeBadge regime={rec.regime} className="mt-1" />
        </div>
      </div>

      {/* Candlestick chart */}
      <Card>
        {chart.length > 0
          ? <CandlestickChart bars={chart} height={320} />
          : <p className="text-gray-500 text-sm text-center py-16">Chart data unavailable.</p>
        }
      </Card>

      {/* Position summary + Fundamentals */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Position Summary">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {[
              ["Entry Price",    fmt(rec.entry_price)],
              ["Stop Loss",      fmt(rec.stop_loss)],
              ["Stop Distance",  stopDistPct],
              ["Position Size",  `$${positionValue.toLocaleString()}`],
              ["Est. Shares",    shares],
              ["Holding Window", rec.holding_window_days ? `${rec.holding_window_days}d` : "—"],
              ["Conviction",     rec.conviction_score ? `${rec.conviction_score.toFixed(1)}/10` : "—"],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-gray-500 text-xs mb-0.5">{label}</dt>
                <dd className="text-gray-100 font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card title="Fundamentals">
          {fundamentals ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              {[
                ["Market Cap",    fmtCap(fundamentals.market_cap)],
                ["P/E Ratio",     fundamentals.pe_ratio ? `${fundamentals.pe_ratio.toFixed(1)}x` : "—"],
                ["Revenue YoY",   fundamentals.revenue_yoy_growth != null
                  ? `${(fundamentals.revenue_yoy_growth * 100).toFixed(1)}%` : "—"],
                ["Analyst",       fundamentals.analyst_consensus || "—"],
                ["Price Target",  fmt(fundamentals.price_target)],
                ["Current Price", fmt(fundamentals.current_price)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-gray-500 text-xs mb-0.5">{label}</dt>
                  <dd className="text-gray-100 font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          ) : <Skeleton className="h-24" />}
        </Card>
      </div>

      {/* Strategy */}
      <Card title="Strategy — Why This Trade">
        <div className="mb-4 flex flex-wrap gap-2">
          {firedSignals.map(s => (
            <span key={s} className="text-xs font-medium bg-accent/15 text-accent px-2 py-1 rounded-full">
              {SIGNAL_LABELS[s] || s}
            </span>
          ))}
        </div>
        {rec.arbiter_summary && (
          <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-line">{rec.arbiter_summary}</p>
        )}
        {Object.keys(techBreak).length > 0 && (
          <div className="mt-4 space-y-1.5">
            <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Signal Details</p>
            {Object.entries(techBreak).map(([name, sig]) => (
              <div key={name} className="flex items-start gap-2 text-xs">
                <span className={`mt-0.5 flex-shrink-0 w-3 h-3 rounded-full ${sig.score ? "bg-green-500" : "bg-gray-700"}`} />
                <span className="text-gray-400 font-medium w-24 flex-shrink-0">{SIGNAL_LABELS[name] || name}</span>
                <span className="text-gray-500">{sig.detail || "—"}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Key Risks */}
      {rec.bear_argument && (
        <Card title="Key Risks">
          <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-line">{rec.bear_argument}</p>
        </Card>
      )}

      {/* Stock News */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Recent News — {rec.ticker}
        </h2>
        {news.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {news.map((a, i) => <NewsItem key={i} article={a} />)}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No recent news.</p>
        )}
      </section>

      {/* Competitor Table */}
      {competitors.length > 0 && (
        <Card title="Competitor Benchmarking">
          <CompetitorTable competitors={competitors} />
        </Card>
      )}
    </div>
  )
}
