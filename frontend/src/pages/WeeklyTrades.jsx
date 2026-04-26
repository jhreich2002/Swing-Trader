import { useEffect, useRef, useState } from "react"
import { api } from "../api/api"
import TradeTile from "../components/recommendations/TradeTile"

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
