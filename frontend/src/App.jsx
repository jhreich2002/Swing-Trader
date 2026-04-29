import { lazy, Suspense } from "react"
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom"
import NavBar from "./components/layout/NavBar"
import Dashboard from "./pages/Dashboard"

const ActivePortfolio      = lazy(() => import("./pages/ActivePortfolio"))
const RothIRA              = lazy(() => import("./pages/RothIRA"))
const PassivePortfolio     = lazy(() => import("./pages/PassivePortfolio"))
const TotalPortfolio       = lazy(() => import("./pages/TotalPortfolio"))
const TradeDetail          = lazy(() => import("./pages/TradeDetail"))
const PortfolioPerformance = lazy(() => import("./pages/PortfolioPerformance"))
const Watchlist            = lazy(() => import("./pages/Watchlist"))
const WatchlistDetail      = lazy(() => import("./pages/WatchlistDetail"))

function RouteFallback() {
  return (
    <div className="flex items-center justify-center py-24 text-gray-500 text-sm">
      <svg className="animate-spin h-5 w-5 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      Loading…
    </div>
  )
}

export default function App() {
  return (
    <Router>
      <div className="min-h-screen bg-surface text-gray-100 flex flex-col">
        <NavBar />
        <main className="flex-1 max-w-screen-xl mx-auto w-full px-4 py-6">
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/"                    element={<Dashboard />} />
              <Route path="/active"              element={<ActivePortfolio />} />
              <Route path="/roth"                element={<RothIRA />} />
              <Route path="/passive"             element={<PassivePortfolio />} />
              <Route path="/portfolios"          element={<TotalPortfolio />} />
              <Route path="/trades"              element={<Navigate to="/active" replace />} />
              <Route path="/trades/:id"          element={<TradeDetail />} />
              <Route path="/watchlist"           element={<Watchlist />} />
              <Route path="/watchlist/:ticker"   element={<WatchlistDetail />} />
              <Route path="/portfolio"           element={<PortfolioPerformance />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </Router>
  )
}
