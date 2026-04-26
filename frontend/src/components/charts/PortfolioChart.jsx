import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts"

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const val = payload[0].value
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 text-sm shadow-lg">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`font-semibold ${val >= 0 ? "text-green-400" : "text-red-400"}`}>
        {val >= 0 ? "+" : ""}{val.toFixed(2)}%
      </p>
      {payload[0].payload.trade_count !== undefined && (
        <p className="text-gray-500 text-xs">{payload[0].payload.trade_count} trades</p>
      )}
    </div>
  )
}

export default function PortfolioChart({ data = [] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3e" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#2a2d3e" }}
          tickFormatter={v => v?.slice(5)}  // MM-DD
        />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#2a2d3e" }}
          tickFormatter={v => `${v}%`}
          width={50}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="4 4" />
        <Line
          type="monotone"
          dataKey="cumulative_return"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: "#3b82f6" }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
