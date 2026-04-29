/**
 * Compact summary card for a single portfolio (used by Total view + page headers).
 * Props:
 *   title, marketValue, costBasis, returnPct, cash, weightPct (optional grand-total %)
 */
function fmtMoney(v) {
  if (v == null || Number.isNaN(v)) return "—"
  return v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })
}

export default function PortfolioSummaryCard({ title, marketValue, costBasis, returnPct, cash, weightPct }) {
  const retColor =
    returnPct == null   ? "text-gray-300" :
    returnPct >= 0      ? "text-green-400" :
                          "text-red-400"
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-widest">{title}</h3>
        {weightPct != null && (
          <span className="text-xs text-gray-500">{weightPct.toFixed(1)}% of total</span>
        )}
      </div>
      <div className="text-3xl font-bold text-gray-100 mb-1">{fmtMoney(marketValue)}</div>
      <div className={`text-sm font-medium ${retColor} mb-3`}>
        {returnPct != null ? (returnPct >= 0 ? "+" : "") + returnPct.toFixed(2) + "%" : "—"}
        <span className="text-gray-500 font-normal"> vs cost</span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-gray-500 uppercase tracking-widest">Cost basis</div>
          <div className="text-gray-300">{fmtMoney(costBasis)}</div>
        </div>
        <div>
          <div className="text-gray-500 uppercase tracking-widest">Cash</div>
          <div className="text-gray-300">{fmtMoney(cash)}</div>
        </div>
      </div>
    </div>
  )
}
