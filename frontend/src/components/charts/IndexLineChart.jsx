import { useEffect, useRef, useState } from "react"
import { createChart, ColorType, LineSeries } from "lightweight-charts"

const SERIES = [
  { key: "spy", label: "SPY (S&P 500)", color: "#3b82f6" },
  { key: "qqq", label: "QQQ (NASDAQ)",  color: "#a78bfa" },
  { key: "dia", label: "DIA (Dow)",     color: "#34d399" },
]

const PERIODS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
]

function sliceData(data, days) {
  if (!data || data.length === 0) return []
  return data.slice(-days)
}

// Normalise a series to % return from its first point (for multi-line comparison)
function normalise(bars) {
  if (bars.length === 0) return []
  const base = bars[0].close
  if (!base) return []
  return bars.map(b => ({ time: b.date, value: parseFloat(((b.close - base) / base * 100).toFixed(3)) }))
}

export default function IndexLineChart({ data }) {
  const containerRef = useRef(null)
  const chartRef     = useRef(null)
  const seriesRefs   = useRef({})
  const [period, setPeriod] = useState(90)

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background:  { type: ColorType.Solid, color: "#1a1d27" },
        textColor:   "#9ca3af",
      },
      grid: {
        vertLines: { color: "#2a2d3e" },
        horzLines: { color: "#2a2d3e" },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: "#2a2d3e" },
      timeScale: { borderColor: "#2a2d3e", timeVisible: true },
      width:  containerRef.current.clientWidth,
      height: 280,
    })
    chartRef.current = chart

    SERIES.forEach(({ key, color }) => {
      seriesRefs.current[key] = chart.addSeries(LineSeries, {
        color,
        lineWidth: 2,
        priceLineVisible: false,
      })
    })

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [])

  // Update series data when data or period changes
  useEffect(() => {
    if (!data || !chartRef.current) return
    SERIES.forEach(({ key }) => {
      const sliced = sliceData(data[key] || [], period)
      seriesRefs.current[key]?.setData(normalise(sliced))
    })
    chartRef.current.timeScale().fitContent()
  }, [data, period])

  return (
    <div className="bg-card rounded-xl border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex gap-4">
          {SERIES.map(({ key, label, color }) => (
            <span key={key} className="flex items-center gap-1.5 text-xs text-gray-400">
              <span className="w-3 h-0.5 rounded" style={{ backgroundColor: color, display: "inline-block" }} />
              {label}
            </span>
          ))}
        </div>
        <div className="flex gap-1">
          {PERIODS.map(({ label, days }) => (
            <button
              key={label}
              onClick={() => setPeriod(days)}
              className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                period === days
                  ? "bg-accent text-white"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="w-full" />
      <p className="text-xs text-gray-500 mt-2 text-right">% return from period start</p>
    </div>
  )
}
