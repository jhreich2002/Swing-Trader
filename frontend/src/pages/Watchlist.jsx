import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { api } from "../api/api"

function fmt(v, { pct = false, dollar = false, decimals = 2 } = {}) {
  if (v == null) return "—"
  const n = parseFloat(v)
  if (isNaN(n)) return "—"
  if (dollar) return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  if (pct) return `${(n * 100).toFixed(1)}%`
  return n.toFixed(decimals)
}

function consensusBadge(c) {
  const map = {
    buy:  "bg-green-900/40 text-green-300 border-green-800",
    hold: "bg-yellow-900/40 text-yellow-300 border-yellow-800",
    sell: "bg-red-900/40 text-red-300 border-red-800",
  }
  return map[c] || "bg-gray-800 text-gray-400 border-gray-700"
}

function statusBadge(s) {
  const map = {
    complete: "bg-green-900/40 text-green-400 border-green-800",
    running:  "bg-blue-900/40 text-blue-300 border-blue-800",
    pending:  "bg-yellow-900/40 text-yellow-400 border-yellow-800",
    error:    "bg-red-900/40 text-red-400 border-red-800",
  }
  return map[s] || "bg-gray-800 text-gray-400 border-gray-700"
}

function Spinner({ size = "h-4 w-4" }) {
  return (
    <svg className={`animate-spin ${size}`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function WatchlistCard({ item, onRemove }) {
  const isReady   = item.digest_status === "complete"
  const isRunning = item.digest_status === "running" || item.digest_status === "pending"

  return (
    <div className="relative bg-card border border-border rounded-xl p-5 hover:border-accent/50 transition-colors group">
      {/* Remove button */}
      <button
        onClick={(e) => { e.preventDefault(); onRemove(item.ticker) }}
        className="absolute top-3 right-3 p-1 rounded text-gray-600 hover:text-red-400 hover:bg-red-900/20 transition-colors opacity-0 group-hover:opacity-100"
        title="Remove from watchlist"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Card content — only clickable if digest is ready */}
      {isReady ? (
        <Link to={`/watchlist/${item.ticker}`} className="block">
          <CardBody item={item} isRunning={isRunning} />
        </Link>
      ) : (
        <CardBody item={item} isRunning={isRunning} />
      )}
    </div>
  )
}

function CardBody({ item, isRunning }) {
  return (
    <>
      <div className="flex items-start justify-between mb-1">
        <div>
          <span className="text-lg font-bold text-white">{item.ticker}</span>
          <p className="text-xs text-gray-500 truncate max-w-[180px]">{item.name}</p>
        </div>
        <div className="text-right">
          {item.current_price != null && (
            <p className="text-sm font-semibold text-white">${parseFloat(item.current_price).toFixed(2)}</p>
          )}
          <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded border font-medium ${statusBadge(item.digest_status)}`}>
            {isRunning ? (
              <span className="flex items-center gap-1"><Spinner size="h-3 w-3" /> Digesting…</span>
            ) : item.digest_status}
          </span>
        </div>
      </div>

      <p className="text-xs text-gray-600 mb-3">{item.sector}</p>

      {item.digest_status === "complete" && (
        <div className="flex items-center justify-between">
          {item.analyst_consensus && (
            <span className={`text-xs px-2 py-0.5 rounded border font-medium ${consensusBadge(item.analyst_consensus)}`}>
              {item.analyst_consensus.toUpperCase()}
            </span>
          )}
          {item.analyst_target && (
            <span className="text-xs text-gray-500">
              Target: <span className="text-gray-300">${parseFloat(item.analyst_target).toFixed(2)}</span>
            </span>
          )}
          <span className="text-xs text-accent font-medium group-hover:underline">View digest →</span>
        </div>
      )}

      {item.digest_status === "error" && (
        <p className="text-xs text-red-400">Digest failed — try refreshing.</p>
      )}
    </>
  )
}

export default function Watchlist() {
  const [items, setItems]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [query, setQuery]       = useState("")
  const [adding, setAdding]     = useState(false)
  const [addMsg, setAddMsg]     = useState(null) // {type: "success"|"error", text}
  const pollRef                 = useRef(null)
  const inputRef                = useRef(null)

  function loadList() {
    api.watchlist.list()
      .then(d => setItems(d.watchlist || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadList()
    // Poll every 5s while any item is pending/running
    pollRef.current = setInterval(() => {
      api.watchlist.list()
        .then(d => {
          const list = d.watchlist || []
          setItems(list)
          const anyActive = list.some(i => i.digest_status === "running" || i.digest_status === "pending")
          if (!anyActive) {
            clearInterval(pollRef.current)
            pollRef.current = null
          }
        })
        .catch(console.error)
    }, 5000)
    return () => clearInterval(pollRef.current)
  }, [])

  // Restart polling whenever items change and some are still running
  useEffect(() => {
    const anyActive = items.some(i => i.digest_status === "running" || i.digest_status === "pending")
    if (anyActive && !pollRef.current) {
      pollRef.current = setInterval(() => {
        api.watchlist.list()
          .then(d => {
            const list = d.watchlist || []
            setItems(list)
            const stillActive = list.some(i => i.digest_status === "running" || i.digest_status === "pending")
            if (!stillActive) {
              clearInterval(pollRef.current)
              pollRef.current = null
            }
          })
          .catch(console.error)
      }, 5000)
    }
  }, [items])

  async function handleAdd(e) {
    e.preventDefault()
    const ticker = query.trim().toUpperCase()
    if (!ticker) return
    setAdding(true)
    setAddMsg(null)
    try {
      const res = await api.watchlist.add(ticker)
      if (res.status === "already_exists") {
        setAddMsg({ type: "info", text: res.message })
      } else {
        setAddMsg({ type: "success", text: res.message })
        setQuery("")
        loadList()
      }
    } catch (e) {
      setAddMsg({ type: "error", text: `Failed to add ${ticker}: ${e.message}` })
    } finally {
      setAdding(false)
      inputRef.current?.focus()
    }
  }

  async function handleRemove(ticker) {
    try {
      await api.watchlist.remove(ticker)
      setItems(prev => prev.filter(i => i.ticker !== ticker))
    } catch (e) {
      console.error(e)
    }
  }

  const msgColors = {
    success: "bg-green-950/40 border-green-800 text-green-300",
    info:    "bg-blue-950/40 border-blue-800 text-blue-300",
    error:   "bg-red-900/20 border-red-800 text-red-400",
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlist</h1>
          <p className="text-sm text-gray-500 mt-0.5">Add any ticker — get a full AI-powered long-term digest</p>
        </div>
        <span className="text-sm text-gray-500">{items.length} ticker{items.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Search / Add bar */}
      <form onSubmit={handleAdd} className="flex gap-3">
        <div className="relative flex-1 max-w-sm">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value.toUpperCase())}
            placeholder="Ticker symbol (e.g. NVDA)"
            className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-card border border-border text-white placeholder-gray-600 text-sm focus:outline-none focus:border-accent transition-colors"
          />
        </div>
        <button
          type="submit"
          disabled={adding || !query.trim()}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-accent hover:bg-accent/80 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {adding ? <Spinner /> : (
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
          )}
          {adding ? "Adding…" : "Add & Digest"}
        </button>
      </form>

      {/* Add message */}
      {addMsg && (
        <div className={`text-sm px-4 py-3 rounded-lg border ${msgColors[addMsg.type]}`}>
          {addMsg.text}
        </div>
      )}

      {/* Watchlist grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="animate-pulse bg-card border border-border rounded-xl h-36" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-24 text-gray-600">
          <svg className="h-12 w-12 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
          </svg>
          <p className="text-lg mb-1">Your watchlist is empty</p>
          <p className="text-sm">Search for a ticker above to get started</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {items.map(item => (
            <WatchlistCard key={item.ticker} item={item} onRemove={handleRemove} />
          ))}
        </div>
      )}
    </div>
  )
}
