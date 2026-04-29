import { useEffect, useRef, useState } from "react"
import { api } from "../api/api"
import TradeTile from "../components/recommendations/TradeTile"
import HypotheticalReturnsChart from "../components/charts/HypotheticalReturnsChart"
import ActualReturnsChart from "../components/charts/ActualReturnsChart"
import PortfolioPieChart from "../components/portfolio/PortfolioPieChart"
import HoldingsEditor from "../components/portfolio/HoldingsEditor"

function getMonday(d = new Date()) {
  const day = d.getDay()
  const diff = d.getDate() - day + (day === 0 ? -6 : 1)
  const mon = new Date(d.setDate(diff))
  return mon.toISOString().slice(0, 10)
}

function offsetWeek(isoMonday, delta) {
  const d = new Date(isoMonday)
  d.setDate(d.getDate() + delta * 7)
  return d.toISOString().slice(0, 10)
}

function fmtWeek(isoMonday) {
  const d = new Date(isoMonday)
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function Skeleton() {
  return <div className="animate-pulse bg-card border border-border rounded-xl h-52" />
}

// Spinner icon
function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

export default function WeeklyTrades() {
  const [week, setWeek]         = useState(getMonday())
  const [recs, setRecs]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  // Dashboard state
  const [hypo,        setHypo]        = useState(null)
  const [hypoLoading, setHypoLoading] = useState(true)
  const [actual,      setActual]      = useState(null)
  const [holdings,    setHoldings]    = useState(null)
  const [actualLoading, setActualLoading] = useState(true)
  const [editorOpen,  setEditorOpen]  = useState(false)

  // Scan button state
  const [scanStatus, setScanStatus] = useState("idle") // idle | running | complete | error
  const [scanMsg, setScanMsg]       = useState("")
  const pollRef                     = useRef(null)

  // Load recommendations whenever week changes
  function loadRecs(targetWeek) {
    setLoading(true)
    setError(null)
    api.recommendations.list(targetWeek)
      .then(d => setRecs(d.recommendations || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadRecs(week)
  }, [week])

  // Dashboard loaders
  function loadHypo() {
    setHypoLoading(true)
    api.recommendations.hypothetical()
      .then(setHypo)
      .catch(() => setHypo(null))
      .finally(() => setHypoLoading(false))
  }

  function loadActual() {
    setActualLoading(true)
    Promise.all([api.portfolio.actual(), api.portfolio.holdings.list()])
      .then(([a, h]) => { setActual(a); setHoldings(h) })
      .catch(() => {})
      .finally(() => setActualLoading(false))
  }

  useEffect(() => {
    loadHypo()
    loadActual()
  }, [])

  // Auto-open editor on first visit if portfolio is empty
  useEffect(() => {
    if (holdings && (holdings.cash === 0 && (holdings.stocks?.length ?? 0) === 0)) {
      setEditorOpen(true)
    }
  }, [holdings])

  // On mount, sync scan status in case a scan is already running
  useEffect(() => {
    api.scan.status()
      .then(s => {
        setScanStatus(s.status)
        setScanMsg(s.message || "")
        if (s.status === "running") startPolling()
      })
      .catch(() => {})
    return () => stopPolling()
  }, [])

  function startPolling() {
    if (pollRef.current) return
    pollRef.current = setInterval(() => {
      api.scan.status().then(s => {
        setScanStatus(s.status)
        setScanMsg(s.message || "")
        if (s.status !== "running") {
          stopPolling()
          if (s.status === "complete") {
            // Jump to current week and reload
            const thisMonday = getMonday()
            setWeek(thisMonday)
            loadRecs(thisMonday)
          }
        }
      }).catch(() => {})
    }, 4000)
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function handleRunScan() {
    if (scanStatus === "running") return
    try {
      const res = await api.scan.run()
      setScanStatus("running")
      setScanMsg(res.message || "Scan in progress…")
      startPolling()
    } catch (e) {
      setScanStatus("error")
      setScanMsg(`Failed to start scan: ${e.message}`)
    }
  }

  const isRunning = scanStatus === "running"

  const scanBtnClass = isRunning
    ? "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-900/40 text-blue-300 border border-blue-700 cursor-not-allowed"
    : "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white border border-blue-500 transition-colors cursor-pointer"

  return (
    <div className="space-y-6">
      {/* Portfolio dashboard */}
      <PortfolioDashboard
        hypo={hypo}
        hypoLoading={hypoLoading}
        actual={actual}
        actualLoading={actualLoading}
        holdings={holdings}
        editorOpen={editorOpen}
        setEditorOpen={setEditorOpen}
        onHoldingsChange={loadActual}
      />

      {/* Header + controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-white">Weekly Trade Ideas</h1>

        <div className="flex items-center gap-3">
          {/* Run Scan button */}
          <button
            onClick={handleRunScan}
            disabled={isRunning}
            className={scanBtnClass}
            title={isRunning ? "Scan in progress…" : "Run a full market scan now"}
          >
            {isRunning ? <Spinner /> : (
              <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
              </svg>
            )}
            {isRunning ? "Scanning…" : "Run Scan"}
          </button>

          {/* Week navigator */}
          <button
            onClick={() => setWeek(w => offsetWeek(w, -1))}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
            title="Previous week"
          >
            ‹
          </button>
          <span className="text-sm text-gray-300 font-medium min-w-[140px] text-center">
            Week of {fmtWeek(week)}
          </span>
          <button
            onClick={() => setWeek(w => offsetWeek(w, 1))}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
            title="Next week"
          >
            ›
          </button>
        </div>
      </div>

      {/* Scan status banner */}
      {scanStatus === "running" && (
        <div className="flex items-center gap-3 bg-blue-950/40 border border-blue-800 rounded-lg px-4 py-3 text-blue-300 text-sm">
          <Spinner />
          <span>Scan running — scanning ~300 tickers through regime, sector, technical, fundamental, and AI debate filters. This takes 10–20 minutes.</span>
        </div>
      )}
      {scanStatus === "complete" && scanMsg && (
        <div className="bg-green-950/40 border border-green-800 rounded-lg px-4 py-3 text-green-300 text-sm">
          Scan complete — recommendations updated.
        </div>
      )}
      {scanStatus === "error" && scanMsg && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">
          {scanMsg}
        </div>
      )}

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <Skeleton key={i} />)}
        </div>
      ) : recs.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <p className="text-lg mb-2">No recommendations for this week.</p>
          <p className="text-sm">Click <span className="text-blue-400 font-medium">Run Scan</span> above to generate trade ideas.</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-gray-500">{recs.length} trade idea{recs.length !== 1 ? "s" : ""} this week, ranked by conviction</p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recs.map(rec => <TradeTile key={rec.id} rec={rec} />)}
          </div>
        </>
      )}
    </div>
  )
}

// ----------------------------------------------------------------------------
// Portfolio dashboard (top of Weekly Trades)
// ----------------------------------------------------------------------------

function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  const sign = v >= 0 ? "+" : ""
  return `${sign}${v.toFixed(2)}%`
}
function pctColor(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "text-gray-400"
  return v >= 0 ? "text-green-400" : "text-red-400"
}

function ChartSkeleton() {
  return <div className="animate-pulse bg-border/40 rounded h-[260px]" />
}

function PortfolioDashboard({
  hypo, hypoLoading,
  actual, actualLoading,
  holdings,
  editorOpen, setEditorOpen,
  onHoldingsChange,
}) {
  const hypoData    = hypo?.data ?? []
  const hypoTotal   = hypo?.total_return_pct
  const actualData  = actual?.history ?? []
  const actualTotal = actual?.return_pct

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Your Portfolio</h2>
        <button
          onClick={() => setEditorOpen(o => !o)}
          className="px-3 py-1.5 rounded-lg text-sm font-medium bg-white/5 hover:bg-white/10 text-gray-200 border border-border transition-colors"
        >
          {editorOpen ? "Hide Holdings" : "Manage Holdings"}
        </button>
      </div>

      {editorOpen && (
        <div className="bg-card border border-border rounded-xl p-5">
          <HoldingsEditor holdings={holdings} onChange={onHoldingsChange} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Hypothetical */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">
              Hypothetical Returns
            </h3>
            <span className={`text-lg font-bold ${pctColor(hypoTotal)}`}>{fmtPct(hypoTotal)}</span>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            If you took every weekly recommendation
            {hypo ? ` — ${hypo.n_trades} trade${hypo.n_trades === 1 ? "" : "s"} (${hypo.n_winners}W / ${hypo.n_losers}L${hypo.n_open ? ` / ${hypo.n_open} open` : ""})` : ""}
          </p>
          {hypoLoading ? (
            <ChartSkeleton />
          ) : hypoData.length > 1 ? (
            <HypotheticalReturnsChart data={hypoData} />
          ) : (
            <div className="h-[260px] flex items-center justify-center text-gray-500 text-sm text-center px-6">
              No completed simulated trades yet. Run a scan to generate recommendations.
            </div>
          )}
        </div>

        {/* Actual */}
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">
              Actual Portfolio
            </h3>
            <span className={`text-lg font-bold ${pctColor(actualTotal)}`}>{fmtPct(actualTotal)}</span>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            {actual?.total_market_value
              ? `${actual.total_market_value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })} market value · ${actual.total_cost_basis.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })} cost basis`
              : "Add cash and stock positions to track returns."}
          </p>
          {actualLoading ? (
            <ChartSkeleton />
          ) : actualData.length > 1 ? (
            <ActualReturnsChart data={actualData} />
          ) : (
            <div className="h-[260px] flex items-center justify-center text-gray-500 text-sm text-center px-6">
              {actual?.total_cost_basis > 0
                ? "Daily snapshots will accumulate here. Check back tomorrow for a curve."
                : "Click Manage Holdings to enter your cash and stock positions."}
            </div>
          )}
        </div>
      </div>

      {/* Pie chart */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">
          Portfolio Weighting
        </h3>
        {actualLoading ? (
          <ChartSkeleton />
        ) : (
          <PortfolioPieChart
            cash={actual?.cash ?? 0}
            cashWeight={actual?.cash_weight_pct ?? 0}
            positions={actual?.positions ?? []}
          />
        )}
      </div>
    </section>
  )
}
