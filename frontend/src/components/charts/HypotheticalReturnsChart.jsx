import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts"

const Tip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const v = payload[0].value
  const tc = payload[0].payload.trade_count
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-2 text-sm shadow-lg">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`font-semibold ${v >= 0 ? "text-green-400" : "text-red-400"}`}>
        {v >= 0 ? "+" : ""}{v.toFixed(2)}%
      </p>
      {tc !== undefined && <p className="text-gray-500 text-xs">{tc} trade{tc === 1 ? "" : "s"}</p>}
    </div>
  )
}

export default function HypotheticalReturnsChart({ data = [] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3e" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#2a2d3e" }}
          tickFormatter={v => v?.slice(5)}
        />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#2a2d3e" }}
          tickFormatter={v => `${v}%`}
          width={50}
        />
        <Tooltip content={<Tip />} />
        <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="4 4" />
        <Line
          type="monotone"
          dataKey="return_pct"
          stroke="#a855f7"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: "#a855f7" }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
