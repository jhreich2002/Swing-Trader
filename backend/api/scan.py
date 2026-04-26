"""
Scan trigger endpoint.

POST /api/scan/run   — starts the full pipeline in a background thread.
GET  /api/scan/status — returns current state: idle | running | complete | error
"""
import logging
import threading
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory state (single-user app — no persistence needed)
# ---------------------------------------------------------------------------
_state: dict = {
    "status":   "idle",      # idle | running | complete | error
    "started":  None,        # ISO timestamp
    "finished": None,        # ISO timestamp
    "message":  "",          # last result summary or error text
}
_lock = threading.Lock()


def _run_scan_bg():
    """Runs backend.run_scan.run() in a background thread and updates _state."""
    with _lock:
        _state["status"]  = "running"
        _state["started"] = datetime.now(timezone.utc).isoformat()
        _state["finished"] = None
        _state["message"] = "Scan in progress…"

    try:
        from backend.run_scan import run
        run()
        msg = "Scan completed successfully."
        status = "complete"
    except Exception as e:
        logger.error("Background scan failed: %s\n%s", e, traceback.format_exc())
        msg = f"Scan error: {e}"
        status = "error"

    with _lock:
        _state["status"]   = status
        _state["finished"] = datetime.now(timezone.utc).isoformat()
        _state["message"]  = msg


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/run")
def start_scan():
    """Start a full scan pipeline. Returns 409 if a scan is already running."""
    with _lock:
        if _state["status"] == "running":
            return {"status": "running", "message": "Scan already in progress."}

    t = threading.Thread(target=_run_scan_bg, daemon=True)
    t.start()
    return {"status": "started", "message": "Scan started in background."}


@router.get("/status")
def scan_status():
    """Return the current scan state."""
    with _lock:
        return dict(_state)
