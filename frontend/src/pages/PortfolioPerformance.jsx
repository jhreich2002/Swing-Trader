import { useEffect, useState } from "react"
import { api } from "../api/api"
import PortfolioChart from "../components/charts/PortfolioChart"
import TradesTable from "../components/portfolio/TradesTable"

function StatCard({ label, value, color = "text-gray-100" }) {
  return (
    <div className="bg-card border border-border rounded-xl px-5 py-4">
      <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  )
}

function Skeleton({ className = "" }) {
  return <div className={`animate-pulse bg-border rounded ${className}`} />
}

export default function PortfolioPerformance() {
  const [perf,    setPerf]    = useState(null)
  const [trades,  setTrades]  = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      api.portfolio.performance(),
      api.portfolio.trades(),
    ]).then(([perfR, tradesR]) => {
      if (perfR.status   === "fulfilled") setPerf(perfR.value)
      if (tradesR.status === "fulfilled") setTrades(tradesR.value.trades || [])
    }).finally(() => setLoading(false))
  }, [])

  const totalReturn = perf?.total_return_pct ?? 0
  const returnColor = totalReturn >= 0 ? "text-green-400" : "text-red-400"
  const returnStr   = totalReturn >= 0 ? `+${totalReturn.toFixed(2)}%` : `${totalReturn.toFixed(2)}%`

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Portfolio Performance</h1>

      {/* Stats row */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total Return"
            value={returnStr}
            color={returnColor}
          />
          <StatCard
            label="Total Trades"
            value={perf?.total_trades ?? 0}
          />
          <StatCard
            label="Win Rate"
            value={perf ? `${perf.win_rate.toFixed(1)}%` : "—"}
            color={perf?.win_rate >= 50 ? "text-green-400" : "text-red-400"}
          />
          <StatCard
            label="W / L"
            value={perf ? `${perf.wins} / ${perf.losses}` : "—"}
          />
        </div>
      )}

      {/* Cumulative return chart */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">
          Cumulative Return
          {perf?.source === "backtest" && (
            <span className="ml-2 text-xs text-yellow-500 normal-case font-normal">(backtest data)</span>
          )}
        </h2>
        {loading ? (
          <Skeleton className="h-72 w-full" />
        ) : (perf?.data?.length ?? 0) > 1 ? (
          <PortfolioChart data={perf.data} />
        ) : (
          <div className="h-72 flex items-center justify-center text-gray-500 text-sm">
            <div className="text-center">
              <p className="mb-2">No closed trade history yet.</p>
              <p className="text-xs">Activate positions and close them to see performance data.</p>
            </div>
          </div>
        )}
      </div>

      {/* Trades table */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">
          Trade History
        </h2>
        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <TradesTable trades={trades} />
        )}
      </div>
    </div>
  )
}
