import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts"

const STOCK_COLORS = [
  "#3b82f6", "#a855f7", "#10b981", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
]
const CASH_COLOR = "#6b7280"

const fmtUSD = v => v?.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })

const Tip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 text-sm shadow-lg">
      <p className="text-gray-200 font-semibold">{p.name}</p>
      <p className="text-gray-400 text-xs">{fmtUSD(p.value)}</p>
      <p className="text-gray-500 text-xs">{p.weight_pct?.toFixed(2)}%</p>
    </div>
  )
}

export default function PortfolioPieChart({ cash = 0, cashWeight = 0, positions = [] }) {
  const slices = []
  if (cash > 0) {
    slices.push({ name: "Cash", value: cash, weight_pct: cashWeight, color: CASH_COLOR })
  }
  positions.forEach((p, i) => {
    if ((p.market_value || 0) > 0) {
      slices.push({
        name:       p.ticker,
        value:      p.market_value,
        weight_pct: p.weight_pct,
        color:      STOCK_COLORS[i % STOCK_COLORS.length],
      })
    }
  })

  if (slices.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center text-gray-500 text-sm">
        Add holdings to see your portfolio weighting.
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={slices}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={95}
          paddingAngle={2}
          stroke="#1a1d2e"
        >
          {slices.map((s, i) => <Cell key={i} fill={s.color} />)}
        </Pie>
        <Tooltip content={<Tip />} />
        <Legend
          verticalAlign="bottom"
          iconType="circle"
          formatter={(value, entry) => (
            <span className="text-gray-300 text-xs">
              {value} <span className="text-gray-500">{entry.payload.weight_pct?.toFixed(1)}%</span>
            </span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
