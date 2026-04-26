import { useEffect, useState } from "react"
import { api } from "../api/api"
import RegimeBadge from "../components/market/RegimeBadge"
import IndexLineChart from "../components/charts/IndexLineChart"
import SynthesisCard from "../components/market/SynthesisCard"
import NewsItem from "../components/market/NewsItem"

function Skeleton({ className = "" }) {
  return <div className={`animate-pulse bg-border rounded ${className}`} />
}

export default function Dashboard() {
  const [regime,    setRegime]    = useState(null)
  const [indices,   setIndices]   = useState(null)
  const [synthesis, setSynthesis] = useState(null)
  const [news,      setNews]      = useState([])
  const [loading,   setLoading]   = useState({ regime: true, indices: true, synthesis: true, news: true })

  useEffect(() => {
    api.market.regime()
      .then(setRegime)
      .catch(console.error)
      .finally(() => setLoading(l => ({ ...l, regime: false })))

    api.market.indices()
      .then(setIndices)
      .catch(console.error)
      .finally(() => setLoading(l => ({ ...l, indices: false })))

    api.market.synthesis()
      .then(setSynthesis)
      .catch(console.error)
      .finally(() => setLoading(l => ({ ...l, synthesis: false })))

    api.market.news()
      .then(d => setNews(d.articles || []))
      .catch(console.error)
      .finally(() => setLoading(l => ({ ...l, news: false })))
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Market Dashboard</h1>
        {loading.regime
          ? <Skeleton className="h-7 w-48" />
          : regime && (
            <RegimeBadge
              regime={regime.regime}
              vix={regime.vix}
              breadthPct={regime.breadth_pct}
            />
          )
        }
      </div>

      {/* Indices chart */}
      <section>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Major Indices
        </h2>
        {loading.indices
          ? <Skeleton className="h-72 w-full rounded-xl" />
          : <IndexLineChart data={indices} />
        }
      </section>

      {/* Two-column: synthesis + news */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* AI Synthesis */}
        <section>
          <SynthesisCard
            synthesis={synthesis?.synthesis}
            themes={synthesis?.themes}
            loading={loading.synthesis}
          />
        </section>

        {/* News feed */}
        <section>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest mb-3">
            Market News
          </h2>
          {loading.news ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)}
            </div>
          ) : (
            <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
              {news.length > 0
                ? news.map((a, i) => <NewsItem key={i} article={a} />)
                : <p className="text-gray-500 text-sm">No news available.</p>
              }
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
