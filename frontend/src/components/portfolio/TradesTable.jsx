import { useState } from "react"

function fmt(v, prefix = "$") {
  if (v == null) return "—"
  return `${prefix}${Number(v).toFixed(2)}`
}

const COLS = [
  { key: "ticker",          label: "Ticker",     align: "left"  },
  { key: "entry_date",      label: "Entry",      align: "left"  },
  { key: "entry_price",     label: "Entry $",    align: "right" },
  { key: "exit_price",      label: "Exit $",     align: "right" },
  { key: "hold_days",       label: "Days",       align: "right" },
  { key: "pnl_pct",         label: "P&L %",      align: "right" },
  { key: "regime",          label: "Regime",     align: "left"  },
  { key: "conviction_score",label: "Conviction", align: "right" },
  { key: "outcome",         label: "Outcome",    align: "left"  },
]

export default function TradesTable({ trades = [] }) {
  const [sortKey, setSortKey] = useState("entry_date")
  const [sortDir, setSortDir] = useState("desc")

  const sorted = [...trades].sort((a, b) => {
    const av = a[sortKey] ?? ""
    const bv = b[sortKey] ?? ""
    return sortDir === "asc"
      ? av > bv ? 1 : -1
      : av < bv ? 1 : -1
  })

  function toggleSort(key) {
    if (sortKey === key) setSortDir(d => d === "asc" ? "desc" : "asc")
    else { setSortKey(key); setSortDir("desc") }
  }

  function SortIcon({ col }) {
    if (sortKey !== col) return <span className="text-gray-700 ml-1">↕</span>
    return <span className="text-accent ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-widest border-b border-border">
            {COLS.map(c => (
              <th
                key={c.key}
                onClick={() => toggleSort(c.key)}
                className={`px-3 py-2 cursor-pointer hover:text-gray-300 select-none ${
                  c.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {c.label}<SortIcon col={c.key} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={COLS.length} className="px-3 py-8 text-center text-gray-500">
                No trades recorded yet.
              </td>
            </tr>
          ) : sorted.map(t => (
            <tr key={t.id} className="border-b border-border/50 hover:bg-white/[0.02]">
              <td className="px-3 py-2 font-mono font-semibold text-gray-200">{t.ticker}</td>
              <td className="px-3 py-2 text-gray-400">{t.entry_date || "—"}</td>
              <td className="px-3 py-2 text-gray-300 text-right">{fmt(t.entry_price)}</td>
              <td className="px-3 py-2 text-gray-300 text-right">{fmt(t.exit_price)}</td>
              <td className="px-3 py-2 text-gray-400 text-right">{t.hold_days ?? "—"}</td>
              <td className={`px-3 py-2 text-right font-medium ${
                (t.pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"
              }`}>
                {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? "+" : ""}${t.pnl_pct.toFixed(2)}%` : "—"}
              </td>
              <td className="px-3 py-2">
                {t.regime ? (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    t.regime === "trending" ? "text-green-400 bg-green-900/30" :
                    t.regime === "bearish"  ? "text-red-400 bg-red-900/30"    :
                    "text-yellow-400 bg-yellow-900/30"
                  }`}>{t.regime}</span>
                ) : "—"}
              </td>
              <td className="px-3 py-2 text-gray-400 text-right">
                {t.conviction_score != null ? t.conviction_score.toFixed(1) : "—"}
              </td>
              <td className="px-3 py-2">
                {t.outcome === "win"  && <span className="text-xs font-semibold text-green-400 bg-green-900/30 px-2 py-0.5 rounded-full">Win</span>}
                {t.outcome === "loss" && <span className="text-xs font-semibold text-red-400 bg-red-900/30 px-2 py-0.5 rounded-full">Loss</span>}
                {t.outcome === "open" && <span className="text-xs font-semibold text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded-full">Open</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
