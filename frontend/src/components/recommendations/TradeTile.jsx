import { Link } from "react-router-dom"

function ConvictionBar({ score }) {
  const pct   = Math.min(100, (score / 10) * 100)
  const color  = score >= 7 ? "bg-green-500" : score >= 5 ? "bg-yellow-500" : "bg-red-500"
  return (
    <div className="mt-3">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>Conviction</span>
        <span className="font-medium text-gray-300">{score?.toFixed(1)}/10</span>
      </div>
      <div className="h-1.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function priceFmt(v) {
  if (v == null) return "—"
  return `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function TradeTile({ rec }) {
  const {
    id, ticker, name, sector, current_price, conviction_score,
    entry_rationale, arbiter_summary, signals_fired = [], regime,
  } = rec

  // Use first sentence of arbiter_summary as the short blurb if no entry_rationale
  const blurb = entry_rationale
    || (arbiter_summary ? arbiter_summary.split(/\.\s+/)[0] + "." : null)

  return (
    <Link
      to={`/trades/${id}`}
      className="block bg-card border border-border rounded-xl p-5 hover:border-accent/60 transition-colors group"
    >
      <div className="flex items-start justify-between mb-1">
        <div>
          <span className="text-lg font-bold text-white group-hover:text-accent transition-colors">
            {ticker}
          </span>
          <p className="text-xs text-gray-500 truncate max-w-[160px]">{name}</p>
        </div>
        <div className="text-right">
          <p className="text-base font-semibold text-gray-100">{priceFmt(current_price)}</p>
          {regime && (
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              regime === "trending" ? "text-green-400 bg-green-900/30" :
              regime === "bearish"  ? "text-red-400 bg-red-900/30"     :
              "text-yellow-400 bg-yellow-900/30"
            }`}>
              {regime}
            </span>
          )}
        </div>
      </div>

      {sector && (
        <p className="text-xs text-gray-600 mb-2">{sector}</p>
      )}

      {signals_fired.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {signals_fired.map(s => (
            <span key={s} className="text-xs bg-accent/10 text-accent/90 px-1.5 py-0.5 rounded">
              {s.toUpperCase()}
            </span>
          ))}
        </div>
      )}

      {blurb && (
        <p className="text-xs text-gray-400 leading-relaxed line-clamp-3">{blurb}</p>
      )}

      <ConvictionBar score={conviction_score} />
    </Link>
  )
}
