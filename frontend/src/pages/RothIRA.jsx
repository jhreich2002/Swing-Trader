import { useEffect, useState } from "react"
import { api } from "../api/api"
import HoldingsEditor from "../components/portfolio/HoldingsEditor"
import PortfolioPieChart from "../components/portfolio/PortfolioPieChart"
import AllocationGauge from "../components/portfolio/AllocationGauge"
import AdvisorPanel from "../components/portfolio/AdvisorPanel"
import PortfolioSummaryCard from "../components/portfolio/PortfolioSummaryCard"
import ActualReturnsChart from "../components/charts/ActualReturnsChart"

const TARGETS = { index: 50, gold_bonds: 10, long_term_hold: 40 }

export default function RothIRA() {
  const scoped = api.portfolio.scope("roth_ira")
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

  const buckets = computeBuckets(actual)
  const longTermCount = (actual?.positions || []).filter(p => (p.bucket || "long_term_hold") === "long_term_hold").length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Roth IRA</h1>
          <p className="text-sm text-gray-500">
            Target: 50% index funds · 10% gold/bonds · 40% across ~5 long-term holds
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
        title="Roth IRA"
        marketValue={actual?.total_market_value}
        costBasis={actual?.total_cost_basis}
        returnPct={actual?.return_pct}
        cash={actual?.cash}
      />

      {editorOpen && (
        <div className="bg-card border border-border rounded-xl p-5">
          <HoldingsEditor
            holdings={holdings}
            onChange={reload}
            portfolioType="roth_ira"
            showBucket
          />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AllocationGauge label="Index Funds" current={buckets.index}          target={TARGETS.index}          color="bg-sky-500" />
        <AllocationGauge label="Gold & Bonds" current={buckets.gold_bonds}     target={TARGETS.gold_bonds}     color="bg-amber-500" />
        <AllocationGauge label="Long-term Holds" current={buckets.long_term_hold} target={TARGETS.long_term_hold} color="bg-violet-500" />
      </div>

      <div className="text-xs text-gray-500 -mt-2">
        {longTermCount} long-term position{longTermCount === 1 ? "" : "s"} (target ≈ 5)
      </div>

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

      <AdvisorPanel portfolioType="roth_ira" title="Roth IRA Advisor" />
    </div>
  )
}

function computeBuckets(actual) {
  const out = { index: 0, gold_bonds: 0, long_term_hold: 0 }
  if (!actual?.positions?.length || !actual.total_market_value) return out
  for (const p of actual.positions) {
    const b = p.bucket || "long_term_hold"
    out[b] = (out[b] || 0) + (p.market_value || 0)
  }
  for (const k of Object.keys(out)) {
    out[k] = (out[k] / actual.total_market_value) * 100
  }
  return out
}
