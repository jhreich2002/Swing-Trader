/**
 * Visualizes current vs target weight for a single bucket.
 * Props:
 *   label:    string
 *   current:  number (percent, e.g. 47.3)
 *   target:   number (percent)
 *   color?:   tailwind bg color class for the bar (default sky)
 */
export default function AllocationGauge({ label, current = 0, target, color = "bg-sky-500" }) {
  const pct = Math.max(0, Math.min(current, 150)) // clamp display
  const delta = target != null ? current - target : null
  const onTarget = target != null && Math.abs(delta) <= 2

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-sm font-medium text-gray-200">{label}</span>
        <span className="text-xs text-gray-500">
          {target != null && <>target <span className="text-gray-400">{target}%</span></>}
        </span>
      </div>

      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-2xl font-bold text-gray-100">{current.toFixed(1)}%</span>
        {delta != null && (
          <span className={`text-xs font-medium ${onTarget ? "text-green-400" : delta > 0 ? "text-amber-400" : "text-sky-400"}`}>
            {delta > 0 ? "+" : ""}{delta.toFixed(1)}% {onTarget ? "on target" : "vs target"}
          </span>
        )}
      </div>

      <div className="relative h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`absolute top-0 left-0 h-full ${color} transition-all`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
        {target != null && (
          <div
            className="absolute top-0 h-full w-0.5 bg-white/60"
            style={{ left: `${Math.min(target, 100)}%` }}
            title={`Target ${target}%`}
          />
        )}
      </div>
    </div>
  )
}
