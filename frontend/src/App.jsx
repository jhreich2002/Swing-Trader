import { BrowserRouter as Router, Routes, Route } from "react-router-dom"
import NavBar from "./components/layout/NavBar"
import Dashboard from "./pages/Dashboard"
import WeeklyTrades from "./pages/WeeklyTrades"
import TradeDetail from "./pages/TradeDetail"
import PortfolioPerformance from "./pages/PortfolioPerformance"
import Watchlist from "./pages/Watchlist"
import WatchlistDetail from "./pages/WatchlistDetail"

export default function App() {
  return (
    <Router>
      <div className="min-h-screen bg-surface text-gray-100 flex flex-col">
        <NavBar />
        <main className="flex-1 max-w-screen-xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/"                    element={<Dashboard />} />
            <Route path="/trades"              element={<WeeklyTrades />} />
            <Route path="/trades/:id"          element={<TradeDetail />} />
            <Route path="/watchlist"           element={<Watchlist />} />
            <Route path="/watchlist/:ticker"   element={<WatchlistDetail />} />
            <Route path="/portfolio"           element={<PortfolioPerformance />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}
