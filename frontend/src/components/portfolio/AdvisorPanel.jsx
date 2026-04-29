import { useEffect, useState } from "react"
import { api } from "../../api/api"

/**
 * AI-driven recommendations panel.
 * Props:
 *   portfolioType: "active" | "roth_ira" | "passive" | "total"
 *   title?: string
 */
export default function AdvisorPanel({ portfolioType, title = "AI Recommendations" }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGen]  = useState(false)
  const [error, setError]     = useState(null)

  const accessor = portfolioType === "total"
    ? api.portfolio.totalRecommendations
    : api.portfolio.scope(portfolioType).recommendations

  async function loadLatest() {
    setLoading(true)
    try {
      setData(await accessor.latest())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function generate() {
    setGen(true)
    setError(null)
    try {
      setData(await accessor.generate())
    } catch (e) {
      setError(e.message)
    } finally {
      setGen(false)
    }
  }

  useEffect(() => { loadLatest() }, [portfolioType])

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-100">{title}</h3>
        <button
          onClick={generate}
          disabled={generating}
          className="px-3 py-1.5 rounded text-sm font-medium bg-purple-600 hover:bg-purple-500 text-white border border-purple-500 disabled:opacity-50"
        >
          {generating ? "Thinking…" : data?.last_generated ? "Regenerate" : "Generate"}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-red-400 text-sm mb-3">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 text-sm">Loading…</div>
      ) : !data?.last_generated ? (
        <div className="text-gray-500 text-sm">
          No recommendations yet. Click <span className="text-gray-300">Generate</span> to ask the advisor.
        </div>
      ) : (
        <>
          {data.summary && (
            <p className="text-gray-300 text-sm mb-4 leading-relaxed">{data.summary}</p>
          )}

          {(data.actions?.length ?? 0) > 0 ? (
            <div className="space-y-2">
              {data.actions.map((a, i) => (
                <ActionRow key={i} action={a} />
              ))}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">No specific actions suggested.</div>
          )}

          <div className="text-xs text-gray-600 mt-4">
            Generated {new Date(data.last_generated).toLocaleString()}
          </div>
        </>
      )}
    </div>
  )
}

function ActionRow({ action }) {
  const verb = (action.action || "").toLowerCase()
  const color =
    verb === "buy"  || verb === "add"  ? "bg-green-900/30 border-green-700 text-green-300" :
    verb === "sell" || verb === "trim" ? "bg-red-900/30 border-red-700 text-red-300" :
                                         "bg-gray-800 border-gray-700 text-gray-300"

  const pct = action.suggested_pct_of_portfolio
  return (
    <div className="border border-border bg-background/40 rounded-lg p-3">
      <div className="flex items-center gap-3 mb-1">
        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase border ${color}`}>
          {action.action}
        </span>
        <span className="text-gray-100 font-semibold">{action.ticker}</span>
        {typeof pct === "number" && (
          <span className="text-xs text-gray-400 ml-auto">target {pct.toFixed(1)}%</span>
        )}
      </div>
      <p className="text-gray-400 text-sm">{action.rationale}</p>
    </div>
  )
}
