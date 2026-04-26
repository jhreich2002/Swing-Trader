"""
Position tracker CLI — run daily (stop checks) and weekly (review).

Commands:
  python -m backend.run_tracker --list
      List all open positions and their current stop levels.

  python -m backend.run_tracker --pending
      List pending recommendations waiting to be entered.

  python -m backend.run_tracker --activate TICKER ENTRY_PRICE SHARES
      Activate a pending recommendation as an open position.
      Options: --rec-id N (link to a specific recommendation ID)
               --config A|B|C (portfolio config, default A)

  python -m backend.run_tracker --check
      Check all open positions: stop hits + trailing stop updates.
      Run this after market close each day.

  python -m backend.run_tracker --close POSITION_ID EXIT_PRICE
      Manually close a position.
      Option: --reason manual|target_reached|expired (default: manual)

  python -m backend.run_tracker --review
      Print weekly P&L review and feed results into Bayesian learning.
      Option: --days N (lookback window, default 7)
"""
import argparse
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("run_tracker")

from backend.database import SessionLocal, Signal, Recommendation
from backend.tracker.positions import (
    activate_position,
    close_position,
    list_open,
    list_pending_recs,
)
from backend.tracker.stop_manager import check_all_stops, check_expirations
from backend.tracker.weekly_review import run_weekly_review, feed_results_to_backtest, print_review


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_open_positions(db):
    positions = list_open(db)
    if not positions:
        print("\n  No open positions.\n")
        return

    header = (
        f"{'ID':>4} {'Ticker':<8} {'Entry':>8} {'Stop':>8} {'CurStop':>8} "
        f"{'Shares':>7} {'Days':>5} {'Config':<6}"
    )
    sep = "=" * len(header)
    print(f"\n{sep}\n  OPEN POSITIONS\n{sep}\n{header}\n{'-'*len(header)}")

    for pos in positions:
        days = (datetime.utcnow() - pos.entry_date).days if pos.entry_date else "--"
        print(
            f"{pos.id:>4} {pos.ticker:<8} "
            f"${pos.entry_price:>7.2f} "
            f"${(pos.stop_loss or 0):>7.2f} "
            f"${(pos.current_stop or 0):>7.2f} "
            f"{(pos.shares or 0):>7.0f} "
            f"{str(days):>5} "
            f"{(pos.portfolio_config or ''):.<6}"
        )
    print(sep + "\n")


def _print_pending_recs(db):
    recs = list_pending_recs(db)
    if not recs:
        print("\n  No pending recommendations.\n")
        return

    header = f"{'ID':>4} {'Ticker':<8} {'Entry $':>9} {'Stop $':>9} {'Window':>7} {'Conv':>5} {'Scanned':<20}"
    sep = "=" * len(header)
    print(f"\n{sep}\n  PENDING RECOMMENDATIONS\n{sep}\n{header}\n{'-'*len(header)}")

    for rec in recs:
        # Resolve ticker from the linked signal
        sig = db.query(Signal).filter(Signal.id == rec.signal_id).first()
        ticker = sig.ticker if sig else "?"
        scanned = sig.scan_date.strftime("%Y-%m-%d %H:%M") if sig and sig.scan_date else "--"

        print(
            f"{rec.id:>4} {ticker:<8} "
            f"${(rec.entry_price or 0):>8.2f} "
            f"${(rec.stop_loss or 0):>8.2f} "
            f"{(rec.holding_window_days or 0):>6}d "
            f"{(rec.conviction_score or 0):>5.1f} "
            f"{scanned:<20}"
        )
    print(sep + "\n")


def _print_stop_results(results: list[dict]):
    if not results:
        print("\n  No open positions to check.\n")
        return

    print(f"\n{'='*60}")
    print("  STOP CHECK RESULTS")
    print(f"{'='*60}")
    for r in results:
        action = r.get("action", "?")
        ticker = r.get("ticker", "?")
        price  = r.get("current_price")
        detail = r.get("detail", "")

        if action == "stopped_out":
            marker = "!! STOPPED OUT"
        elif action == "stop_trailed":
            marker = "^^ Stop trailed"
        elif action == "no_change":
            marker = "   No change   "
        else:
            marker = f"   {action}"

        price_str = f"${price:.2f}" if price else "N/A"
        print(f"  {marker}  {ticker:<8}  {price_str:>8}  {detail}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_list(args, db):
    _print_open_positions(db)


def cmd_pending(args, db):
    _print_pending_recs(db)


def cmd_activate(args, db):
    ticker       = args.ticker.upper()
    entry_price  = args.entry_price
    shares       = args.shares
    rec_id       = getattr(args, "rec_id", None)
    config       = getattr(args, "config", "A") or "A"

    try:
        pos = activate_position(
            ticker           = ticker,
            entry_price      = entry_price,
            shares           = shares,
            db               = db,
            portfolio_config = config,
            recommendation_id = rec_id,
        )
        print(f"\n  Position opened: {ticker}  entry=${entry_price:.2f}  "
              f"stop=${(pos.current_stop or 0):.2f}  shares={shares:.0f}\n")
    except ValueError as e:
        print(f"\n  Error: {e}\n")
        sys.exit(1)


def cmd_check(args, db):
    print("\nChecking stops for all open positions...")
    results = check_all_stops(db)
    _print_stop_results(results)

    expired = check_expirations(db)
    if expired:
        print("  HOLDING WINDOW ALERTS:")
        for e in expired:
            print(f"    {e['ticker']}  (pos_id={e['position_id']})  "
                  f"held {e['days_held']}d / {e['max_days']}d max — consider closing")
        print()


def cmd_close(args, db):
    reason = getattr(args, "reason", "manual") or "manual"
    try:
        pos = close_position(args.position_id, args.exit_price, reason, db)
        print(f"\n  Closed: {pos.ticker}  exit=${pos.exit_price:.2f}  "
              f"P&L={pos.pnl:+.1f}%  reason={reason}\n")
    except ValueError as e:
        print(f"\n  Error: {e}\n")
        sys.exit(1)


def cmd_review(args, db):
    days = getattr(args, "days", 7) or 7
    print(f"\nRunning weekly review (last {days} days)...")
    summary = run_weekly_review(db, lookback_days=days)
    print_review(summary)

    if summary["closed"]:
        fed = feed_results_to_backtest(db, lookback_days=days)
        if fed:
            print(f"  {fed} trade outcomes fed into backtest_results.")
            print("  Run 'python -m backend.run_backtest' to refresh Bayesian weights.\n")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.run_tracker",
        description="Swing trade position tracker",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list",    help="List all open positions")
    sub.add_parser("pending", help="List pending recommendations")

    act = sub.add_parser("activate", help="Activate a pending recommendation")
    act.add_argument("ticker",      type=str,   help="Ticker symbol (e.g. AAPL)")
    act.add_argument("entry_price", type=float, help="Confirmed entry price")
    act.add_argument("shares",      type=float, help="Number of shares entered")
    act.add_argument("--rec-id",   dest="rec_id", type=int, default=None,
                     help="Recommendation ID to link (optional, auto-detected otherwise)")
    act.add_argument("--config",   type=str, default="A", choices=["A","B","C"],
                     help="Portfolio configuration (default: A)")

    sub.add_parser("check", help="Check stops and trail for all open positions")

    cls = sub.add_parser("close", help="Manually close an open position")
    cls.add_argument("position_id", type=int,   help="Position ID from --list")
    cls.add_argument("exit_price",  type=float, help="Exit price")
    cls.add_argument("--reason",   type=str,   default="manual",
                     choices=["manual","target_reached","expired","stop_hit"],
                     help="Reason for closing (default: manual)")

    rev = sub.add_parser("review", help="Weekly P&L review + Bayesian feedback")
    rev.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")

    return parser


def run():
    parser = build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    db = SessionLocal()
    try:
        {
            "list":     cmd_list,
            "pending":  cmd_pending,
            "activate": cmd_activate,
            "check":    cmd_check,
            "close":    cmd_close,
            "review":   cmd_review,
        }[args.command](args, db)
    finally:
        db.close()


if __name__ == "__main__":
    run()
