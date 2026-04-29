import { useEffect, useState } from "react"
import { api } from "../api/api"
import HoldingsEditor from "../components/portfolio/HoldingsEditor"
import PortfolioPieChart from "../components/portfolio/PortfolioPieChart"
import AdvisorPanel from "../components/portfolio/AdvisorPanel"
import PortfolioSummaryCard from "../components/portfolio/PortfolioSummaryCard"
import ActualReturnsChart from "../components/charts/ActualReturnsChart"

export default function PassivePortfolio() {
  const scoped = api.portfolio.scope("passive")
  const [actual, setActual]     = useState(null)
  const [holdings, setHoldings] = useState(null)
  const [loading, setLoading]   = useState(true)
  const [editorOpen, setEditorOpen] = useState(false)

  function reload() {
    setLoading(true)
    Promise.all([scoped.actual(), scoped.holdings.list()])
      .then(([a, h]) => { setActual(a); setHoldings(h) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }
  useEffect(reload, [])
  useEffect(() => {
    if (holdings && holdings.cash === 0 && (holdings.stocks?.length ?? 0) === 0) {
      setEditorOpen(true)
    }
  }, [holdings])

  const top = (actual?.positions || []).slice().sort((a, b) => (b.weight_pct || 0) - (a.weight_pct || 0))[0]
  const concentrationRisk = top && (top.weight_pct || 0) > 20

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Passive Portfolio</h1>
          <p className="text-sm text-gray-500">
            The bulk of net worth — long-term growth stocks &amp; index funds, low turnover.
          </p>
        </div>
        <button
          onClick={() => setEditorOpen(o => !o)}
          className="px-3 py-1.5 rounded-lg text-sm font-medium bg-white/5 hover:bg-white/10 text-gray-200 border border-border"
        >
          {editorOpen ? "Hide Holdings" : "Manage Holdings"}
        </button>
      </div>

      <PortfolioSummaryCard
        title="Passive"
        marketValue={actual?.total_market_value}
        costBasis={actual?.total_cost_basis}
        returnPct={actual?.return_pct}
        cash={actual?.cash}
      />

      {concentrationRisk && (
        <div className="bg-amber-950/40 border border-amber-700 rounded-lg px-4 py-3 text-amber-300 text-sm">
          ⚠ Concentration risk — <span className="font-semibold">{top.ticker}</span> is {top.weight_pct.toFixed(1)}% of this portfolio (over 20%).
        </div>
      )}

      {editorOpen && (
        <div className="bg-card border border-border rounded-xl p-5">
          <HoldingsEditor holdings={holdings} onChange={reload} portfolioType="passive" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">Returns</h3>
          {loading ? (
            <div className="animate-pulse h-[260px] bg-border/40 rounded" />
          ) : (actual?.history?.length ?? 0) > 1 ? (
            <ActualReturnsChart data={actual.history} />
          ) : (
            <div className="h-[260px] flex items-center justify-center text-gray-500 text-sm">
              {actual?.total_cost_basis > 0 ? "Snapshots accumulate daily." : "Add holdings to start tracking."}
            </div>
          )}
        </div>

        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">Weighting</h3>
          {loading ? (
            <div className="animate-pulse h-[260px] bg-border/40 rounded" />
          ) : (
            <PortfolioPieChart
              cash={actual?.cash ?? 0}
              cashWeight={actual?.cash_weight_pct ?? 0}
              positions={actual?.positions ?? []}
            />
          )}
        </div>
      </div>

      <AdvisorPanel portfolioType="passive" title="Passive Portfolio Advisor" />
    </div>
  )
}
