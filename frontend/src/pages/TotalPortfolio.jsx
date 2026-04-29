import { useEffect, useState } from "react"
import { api } from "../api/api"
import PortfolioSummaryCard from "../components/portfolio/PortfolioSummaryCard"
import AdvisorPanel from "../components/portfolio/AdvisorPanel"
import ActualReturnsChart from "../components/charts/ActualReturnsChart"

const PTYPE_LABELS = { active: "Active", roth_ira: "Roth IRA", passive: "Passive" }

function fmtMoney(v) {
  if (v == null) return "—"
  return v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })
}

export default function TotalPortfolio() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  function reload() {
    setLoading(true)
    api.portfolio.total()
      .then(d => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(reload, [])

  if (loading) return <div className="text-gray-500 text-sm py-12 text-center">Loading total portfolio…</div>
  if (error)   return <div className="bg-red-900/20 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>
  if (!data)   return null

  const history = data.history || []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Total Portfolio</h1>
        <p className="text-sm text-gray-500">Aggregate view across Active, Roth IRA, and Passive accounts.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <PortfolioSummaryCard
          title="Grand Total"
          marketValue={data.grand_total_market_value}
          costBasis={data.grand_total_cost_basis}
          returnPct={data.grand_return_pct}
          cash={data.portfolios.reduce((s, p) => s + (p.cash || 0), 0)}
        />
        {data.portfolios.map(p => (
          <PortfolioSummaryCard
            key={p.portfolio_type}
            title={PTYPE_LABELS[p.portfolio_type] || p.portfolio_type}
            marketValue={p.total_market_value}
            costBasis={p.total_cost_basis}
            returnPct={p.return_pct}
            cash={p.cash}
            weightPct={p.weight_of_grand_total_pct}
          />
        ))}
      </div>

      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">Total Returns</h3>
        {history.length > 1 ? (
          <ActualReturnsChart data={history.map(h => ({ date: h.date, return_pct: h.grand_return_pct, total_value: h.total_value }))} />
        ) : (
          <div className="h-[260px] flex items-center justify-center text-gray-500 text-sm">Snapshots accumulate daily.</div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ExposureCard
          title="Sector Exposure"
          rows={data.sector_exposure}
          labelKey="sector"
        />
        <ExposureCard
          title="Asset-Class Exposure"
          rows={data.asset_class_exposure.map(r => ({ ...r, sector: ASSET_LABELS[r.class] || r.class }))}
          labelKey="sector"
        />
      </div>

      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">Concentration</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Stat label="Top 5 positions" value={`${data.concentration.top_5_weight_pct.toFixed(1)}%`} />
          <Stat label="Largest single position" value={`${data.concentration.max_single_position_pct.toFixed(1)}%`} />
          <Stat label="Largest sector" value={`${data.concentration.max_single_sector_pct.toFixed(1)}%`} />
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">
          Combined Positions ({data.combined_positions.length})
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs uppercase tracking-widest">
                <th className="text-left font-normal pb-2">Ticker</th>
                <th className="text-right font-normal pb-2">Shares</th>
                <th className="text-right font-normal pb-2">Market Value</th>
                <th className="text-right font-normal pb-2">Weight</th>
                <th className="text-right font-normal pb-2">Active</th>
                <th className="text-right font-normal pb-2">Roth</th>
                <th className="text-right font-normal pb-2">Passive</th>
              </tr>
            </thead>
            <tbody>
              {data.combined_positions.map(pos => (
                <tr key={pos.ticker} className="border-t border-border/50">
                  <td className="py-2 text-gray-200 font-medium">{pos.ticker}</td>
                  <td className="py-2 text-right text-gray-300">{pos.total_shares.toFixed(2)}</td>
                  <td className="py-2 text-right text-gray-300">{fmtMoney(pos.total_market_value)}</td>
                  <td className="py-2 text-right text-gray-400">{pos.weight_pct.toFixed(2)}%</td>
                  <td className="py-2 text-right text-gray-500">{pos.by_portfolio.active ? fmtMoney(pos.by_portfolio.active) : "—"}</td>
                  <td className="py-2 text-right text-gray-500">{pos.by_portfolio.roth_ira ? fmtMoney(pos.by_portfolio.roth_ira) : "—"}</td>
                  <td className="py-2 text-right text-gray-500">{pos.by_portfolio.passive ? fmtMoney(pos.by_portfolio.passive) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <AdvisorPanel portfolioType="total" title="Cross-Portfolio Advisor" />
    </div>
  )
}

const ASSET_LABELS = { equity: "Equity", bonds_gold: "Bonds & Gold", cash: "Cash" }

function Stat({ label, value }) {
  return (
    <div className="bg-background/40 border border-border rounded-lg p-3">
      <div className="text-xs text-gray-500 uppercase tracking-widest">{label}</div>
      <div className="text-2xl font-bold text-gray-100 mt-1">{value}</div>
    </div>
  )
}

function ExposureCard({ title, rows, labelKey = "sector" }) {
  const max = Math.max(1, ...rows.map(r => r.weight_pct || 0))
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">{title}</h3>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i}>
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-gray-300">{r[labelKey]}</span>
              <span className="text-gray-500 text-xs">{(r.weight_pct ?? 0).toFixed(1)}%</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-sky-500" style={{ width: `${((r.weight_pct || 0) / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
