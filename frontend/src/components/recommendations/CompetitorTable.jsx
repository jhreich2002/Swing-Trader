function fmt(v, decimals = 1, suffix = "") {
  if (v == null) return "—"
  return `${Number(v).toFixed(decimals)}${suffix}`
}

function fmtCap(v) {
  if (v == null) return "—"
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(0)}B`
  return `$${(v / 1e6).toFixed(0)}M`
}

function ReturnCell({ value }) {
  if (value == null) return <td className="px-3 py-2 text-gray-500 text-sm">—</td>
  const color = value >= 0 ? "text-green-400" : "text-red-400"
  return (
    <td className={`px-3 py-2 text-sm font-medium ${color}`}>
      {value >= 0 ? "+" : ""}{value.toFixed(1)}%
    </td>
  )
}

export default function CompetitorTable({ competitors = [] }) {
  if (competitors.length === 0) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-widest border-b border-border">
            <th className="px-3 py-2 text-left">Company</th>
            <th className="px-3 py-2 text-left">Ticker</th>
            <th className="px-3 py-2 text-right">Mkt Cap</th>
            <th className="px-3 py-2 text-right">P/E</th>
            <th className="px-3 py-2 text-right">Rev YoY</th>
            <th className="px-3 py-2 text-right">52W Return</th>
          </tr>
        </thead>
        <tbody>
          {competitors.map(c => (
            <tr
              key={c.ticker}
              className={`border-b border-border/50 last:border-0 ${
                c.is_subject ? "bg-accent/5 border-l-2 border-l-accent" : "hover:bg-white/[0.02]"
              }`}
            >
              <td className="px-3 py-2 text-gray-200 font-medium truncate max-w-[160px]">
                {c.name}
                {c.is_subject && (
                  <span className="ml-2 text-xs text-accent">(this stock)</span>
                )}
              </td>
              <td className="px-3 py-2 text-gray-400 font-mono">{c.ticker}</td>
              <td className="px-3 py-2 text-gray-300 text-right">{fmtCap(c.market_cap)}</td>
              <td className="px-3 py-2 text-gray-300 text-right">{fmt(c.pe_ratio, 1, "x")}</td>
              <td className="px-3 py-2 text-right">
                {c.revenue_yoy_growth == null ? (
                  <span className="text-gray-500">—</span>
                ) : (
                  <span className={c.revenue_yoy_growth >= 0 ? "text-green-400" : "text-red-400"}>
                    {c.revenue_yoy_growth >= 0 ? "+" : ""}
                    {(c.revenue_yoy_growth * 100).toFixed(1)}%
                  </span>
                )}
              </td>
              <ReturnCell value={c.return_52w} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
