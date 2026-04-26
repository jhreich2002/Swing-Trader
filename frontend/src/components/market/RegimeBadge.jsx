const COLORS = {
  trending: "bg-green-900/50 text-green-400 border-green-700",
  choppy:   "bg-yellow-900/50 text-yellow-400 border-yellow-700",
  bearish:  "bg-red-900/50 text-red-400 border-red-700",
  unknown:  "bg-gray-800 text-gray-400 border-gray-600",
}

export default function RegimeBadge({ regime, vix, breadthPct, className = "" }) {
  const color = COLORS[regime] || COLORS.unknown
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-semibold ${color} ${className}`}>
      <span className="uppercase tracking-widest">{regime || "unknown"}</span>
      {vix !== undefined && vix !== null && (
        <span className="opacity-75">VIX {Number(vix).toFixed(1)}</span>
      )}
      {breadthPct !== undefined && breadthPct !== null && (
        <span className="opacity-75">{Number(breadthPct).toFixed(0)}% above 200MA</span>
      )}
    </span>
  )
}
