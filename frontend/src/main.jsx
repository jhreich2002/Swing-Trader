import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Kick off the slowest dashboard request as early as possible so the response
// is already in the HTTP cache by the time Dashboard mounts.
const _apiBase = import.meta.env.VITE_API_URL || ""
try {
  fetch(`${_apiBase}/api/market/synthesis`, { credentials: "omit" }).catch(() => {})
} catch { /* ignore */ }

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
