import { useEffect, useRef } from "react"
import { createChart, ColorType, CandlestickSeries } from "lightweight-charts"

export default function CandlestickChart({ bars = [], height = 320 }) {
  const containerRef = useRef(null)
  const chartRef     = useRef(null)
  const seriesRef    = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#1a1d27" },
        textColor:  "#9ca3af",
      },
      grid: {
        vertLines: { color: "#2a2d3e" },
        horzLines: { color: "#2a2d3e" },
      },
      crosshair:       { mode: 1 },
      rightPriceScale: { borderColor: "#2a2d3e" },
      timeScale:       { borderColor: "#2a2d3e", timeVisible: true },
      width:  containerRef.current.clientWidth,
      height,
    })
    chartRef.current = chart
    seriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor:      "#34d399",
      downColor:    "#f87171",
      borderVisible: false,
      wickUpColor:   "#34d399",
      wickDownColor: "#f87171",
    })

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [height])

  useEffect(() => {
    if (!seriesRef.current || bars.length === 0) return
    const formatted = bars.map(b => ({
      time:  b.time,
      open:  b.open,
      high:  b.high,
      low:   b.low,
      close: b.close,
    }))
    seriesRef.current.setData(formatted)
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  return <div ref={containerRef} className="w-full" />
}
