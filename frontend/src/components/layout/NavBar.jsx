import { NavLink } from "react-router-dom"

const links = [
  { to: "/",            label: "Dashboard" },
  { to: "/active",      label: "Active Portfolio" },
  { to: "/roth",        label: "Roth IRA" },
  { to: "/passive",     label: "Passive" },
  { to: "/portfolios",  label: "Total" },
  { to: "/watchlist",   label: "Watchlist" },
]

export default function NavBar() {
  return (
    <nav className="bg-card border-b border-border sticky top-0 z-50">
      <div className="max-w-screen-xl mx-auto px-4 h-14 flex items-center justify-between">
        <span className="text-white font-semibold text-lg tracking-tight">
          Swing Trader
        </span>
        <div className="flex gap-1">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-accent text-white"
                    : "text-gray-400 hover:text-white hover:bg-white/5"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  )
}
