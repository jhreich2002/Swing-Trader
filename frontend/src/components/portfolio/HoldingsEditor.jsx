import { useEffect, useState } from "react"
import { api } from "../../api/api"

const BUCKETS = [
  { value: "index",          label: "Index" },
  { value: "gold_bonds",     label: "Gold/Bonds" },
  { value: "long_term_hold", label: "Long-term hold" },
]

const _INDEX_TICKERS = new Set(["SPY","VOO","IVV","VTI","QQQ","SCHB","SCHX","VEA","VXUS","IEFA","EFA","ITOT","SPLG"])
const _GOLD_BOND_TICKERS = new Set(["GLD","IAU","SGOL","TLT","IEF","AGG","BND","LQD","SHY","GOVT","BNDX","TIP"])

function classifyBucket(ticker) {
  const t = (ticker || "").toUpperCase()
  if (_INDEX_TICKERS.has(t)) return "index"
  if (_GOLD_BOND_TICKERS.has(t)) return "gold_bonds"
  return "long_term_hold"
}

function NumInput({ value, onChange, placeholder, className = "" }) {
  return (
    <input
      type="number"
      step="any"
      min="0"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className={`bg-background border border-border rounded px-2 py-1 text-sm text-gray-100 w-full focus:outline-none focus:border-blue-500 ${className}`}
    />
  )
}

function TextInput({ value, onChange, placeholder, className = "" }) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value.toUpperCase())}
      placeholder={placeholder}
      className={`bg-background border border-border rounded px-2 py-1 text-sm text-gray-100 w-full uppercase focus:outline-none focus:border-blue-500 ${className}`}
    />
  )
}

function BucketSelect({ value, onChange, className = "" }) {
  return (
    <select
      value={value || "long_term_hold"}
      onChange={e => onChange(e.target.value)}
      className={`bg-background border border-border rounded px-2 py-1 text-sm text-gray-100 w-full focus:outline-none focus:border-blue-500 ${className}`}
    >
      {BUCKETS.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
    </select>
  )
}

export default function HoldingsEditor({ holdings, onChange, portfolioType = "active", showBucket = false }) {
  const scoped = api.portfolio.scope(portfolioType)
  const [cashDraft, setCashDraft] = useState(String(holdings?.cash ?? 0))
  const [savingCash, setSavingCash] = useState(false)
  const [newTicker, setNewTicker] = useState("")
  const [newShares, setNewShares] = useState("")
  const [newCost, setNewCost] = useState("")
  const [newBucket, setNewBucket] = useState("long_term_hold")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setCashDraft(String(holdings?.cash ?? 0))
  }, [holdings?.cash])

  useEffect(() => {
    if (showBucket) setNewBucket(classifyBucket(newTicker))
  }, [newTicker, showBucket])

  async function saveCash() {
    const amount = parseFloat(cashDraft)
    if (Number.isNaN(amount) || amount < 0) return
    if (amount === holdings?.cash) return
    setSavingCash(true)
    setError(null)
    try {
      await scoped.holdings.setCash(amount)
      onChange?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingCash(false)
    }
  }

  async function addStock() {
    const ticker = newTicker.trim().toUpperCase()
    const shares = parseFloat(newShares)
    const cost   = parseFloat(newCost)
    if (!ticker || Number.isNaN(shares) || shares <= 0 || Number.isNaN(cost) || cost < 0) {
      setError("Enter ticker, shares (>0), and cost basis.")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const body = { ticker, shares, cost_basis_per_share: cost }
      if (showBucket) body.bucket = newBucket
      await scoped.holdings.upsertStock(body)
      setNewTicker("")
      setNewShares("")
      setNewCost("")
      setNewBucket("long_term_hold")
      onChange?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeStock(id) {
    setBusy(true)
    setError(null)
    try {
      await scoped.holdings.remove(id)
      onChange?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function updateStock(stock, patch) {
    setBusy(true)
    setError(null)
    try {
      await scoped.holdings.patchStock(stock.id, patch)
      onChange?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg px-3 py-2 text-red-400 text-sm">
          {error}
        </div>
      )}

      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-widest mb-1">Cash ($)</label>
        <div className="flex items-center gap-2 max-w-sm">
          <NumInput value={cashDraft} onChange={setCashDraft} placeholder="0" />
          <button
            onClick={saveCash}
            disabled={savingCash}
            className="px-3 py-1 rounded text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white border border-blue-500 disabled:opacity-50"
          >
            {savingCash ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-widest mb-2">Stock Positions</label>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-xs uppercase tracking-widest">
                <th className="text-left font-normal pb-2 pr-3">Ticker</th>
                <th className="text-right font-normal pb-2 pr-3">Shares</th>
                <th className="text-right font-normal pb-2 pr-3">Cost / share</th>
                {showBucket && <th className="text-left font-normal pb-2 pr-3">Bucket</th>}
                <th className="pb-2 w-10"></th>
              </tr>
            </thead>
            <tbody>
              {(holdings?.stocks ?? []).map(s => (
                <StockRow
                  key={s.id}
                  stock={s}
                  onUpdate={updateStock}
                  onRemove={removeStock}
                  disabled={busy}
                  showBucket={showBucket}
                />
              ))}
              <tr className="border-t border-border">
                <td className="pt-2 pr-3"><TextInput value={newTicker} onChange={setNewTicker} placeholder="AAPL" /></td>
                <td className="pt-2 pr-3"><NumInput value={newShares} onChange={setNewShares} placeholder="10" /></td>
                <td className="pt-2 pr-3"><NumInput value={newCost} onChange={setNewCost} placeholder="180.00" /></td>
                {showBucket && (
                  <td className="pt-2 pr-3"><BucketSelect value={newBucket} onChange={setNewBucket} /></td>
                )}
                <td className="pt-2 text-right">
                  <button
                    onClick={addStock}
                    disabled={busy}
                    className="px-3 py-1 rounded text-sm font-medium bg-green-600 hover:bg-green-500 text-white border border-green-500 disabled:opacity-50"
                    title="Add position"
                  >+</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function StockRow({ stock, onUpdate, onRemove, disabled, showBucket }) {
  const [shares, setShares] = useState(String(stock.shares))
  const [cost,   setCost]   = useState(String(stock.cost_basis_per_share))

  useEffect(() => { setShares(String(stock.shares)) }, [stock.shares])
  useEffect(() => { setCost(String(stock.cost_basis_per_share)) }, [stock.cost_basis_per_share])

  function commitShares() {
    const v = parseFloat(shares)
    if (!Number.isNaN(v) && v > 0 && v !== stock.shares) onUpdate(stock, { shares: v })
  }
  function commitCost() {
    const v = parseFloat(cost)
    if (!Number.isNaN(v) && v >= 0 && v !== stock.cost_basis_per_share) onUpdate(stock, { cost_basis_per_share: v })
  }

  return (
    <tr className="border-t border-border/50">
      <td className="py-2 pr-3 text-gray-200 font-medium">{stock.ticker}</td>
      <td className="py-2 pr-3">
        <input
          type="number"
          step="any"
          min="0"
          value={shares}
          onChange={e => setShares(e.target.value)}
          onBlur={commitShares}
          className="bg-background border border-border rounded px-2 py-1 text-sm text-gray-100 w-full text-right focus:outline-none focus:border-blue-500"
        />
      </td>
      <td className="py-2 pr-3">
        <input
          type="number"
          step="any"
          min="0"
          value={cost}
          onChange={e => setCost(e.target.value)}
          onBlur={commitCost}
          className="bg-background border border-border rounded px-2 py-1 text-sm text-gray-100 w-full text-right focus:outline-none focus:border-blue-500"
        />
      </td>
      {showBucket && (
        <td className="py-2 pr-3">
          <BucketSelect
            value={stock.bucket}
            onChange={v => onUpdate(stock, { bucket: v })}
          />
        </td>
      )}
      <td className="py-2 text-right">
        <button
          onClick={() => onRemove(stock.id)}
          disabled={disabled}
          className="text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50"
          title="Remove"
        >×</button>
      </td>
    </tr>
  )
}
