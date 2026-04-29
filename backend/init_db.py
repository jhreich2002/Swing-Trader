"""
Run this once to create all database tables and seed initial Bayesian weights.
Safe to re-run — uses checkfirst=True so existing tables are not dropped,
and seed_initial_weights() skips regimes that already have weight rows.
"""
from backend.database import Base, engine, SessionLocal
from backend.config import DATABASE_URL


def _ensure_target_price_column():
    """
    Idempotent ALTER TABLE for the new `recommendations.target_price` column
    on pre-existing databases. SQLAlchemy's create_all() does not add columns
    to existing tables, so we patch them in here.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "recommendations" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("recommendations")}
    if "target_price" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE recommendations ADD COLUMN target_price FLOAT"))
    print("  + added column recommendations.target_price")


def _ensure_portfolio_columns():
    """
    Idempotent ALTERs to add multi-portfolio support to existing tables.
    Safe to re-run; backfills `portfolio_type='active'` for legacy rows.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    # holdings: add portfolio_type, bucket
    if "holdings" in tables:
        cols = {c["name"] for c in insp.get_columns("holdings")}
        with engine.begin() as conn:
            if "portfolio_type" not in cols:
                conn.execute(text(
                    "ALTER TABLE holdings ADD COLUMN portfolio_type VARCHAR(20) NOT NULL DEFAULT 'active'"
                ))
                print("  + added column holdings.portfolio_type")
            if "bucket" not in cols:
                conn.execute(text("ALTER TABLE holdings ADD COLUMN bucket VARCHAR(20)"))
                print("  + added column holdings.bucket")
            # Backfill any rows the DEFAULT didn't catch
            conn.execute(text(
                "UPDATE holdings SET portfolio_type = 'active' WHERE portfolio_type IS NULL"
            ))

    # portfolio_snapshots: add portfolio_type; replace single-col uniqueness
    # with composite (portfolio_type, snapshot_date)
    if "portfolio_snapshots" in tables:
        cols = {c["name"] for c in insp.get_columns("portfolio_snapshots")}
        with engine.begin() as conn:
            if "portfolio_type" not in cols:
                conn.execute(text(
                    "ALTER TABLE portfolio_snapshots ADD COLUMN portfolio_type VARCHAR(20) NOT NULL DEFAULT 'active'"
                ))
                print("  + added column portfolio_snapshots.portfolio_type")
            conn.execute(text(
                "UPDATE portfolio_snapshots SET portfolio_type = 'active' WHERE portfolio_type IS NULL"
            ))

        # Drop legacy single-column unique on snapshot_date if present, then
        # ensure composite unique (portfolio_type, snapshot_date) exists.
        # Index/constraint names differ across Postgres/SQLite — try a few.
        from sqlalchemy.exc import OperationalError, ProgrammingError
        candidates_to_drop = [
            "ix_portfolio_snapshots_snapshot_date",
            "portfolio_snapshots_snapshot_date_key",
            "uq_portfolio_snapshots_snapshot_date",
            "sqlite_autoindex_portfolio_snapshots_1",
        ]
        is_sqlite = DATABASE_URL.startswith("sqlite")
        with engine.begin() as conn:
            for name in candidates_to_drop:
                try:
                    if is_sqlite:
                        conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                    else:
                        # Postgres: try as constraint first, then as index
                        try:
                            conn.execute(text(
                                f'ALTER TABLE portfolio_snapshots DROP CONSTRAINT IF EXISTS "{name}"'
                            ))
                        except (OperationalError, ProgrammingError):
                            pass
                        conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                except (OperationalError, ProgrammingError):
                    pass

            # Re-create the snapshot_date index (non-unique) and composite unique
            try:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_snapshot_date "
                    "ON portfolio_snapshots (snapshot_date)"
                ))
            except (OperationalError, ProgrammingError):
                pass
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_snapshot_per_day "
                    "ON portfolio_snapshots (portfolio_type, snapshot_date)"
                ))
            except (OperationalError, ProgrammingError) as e:
                # If duplicates exist (extremely unlikely), surface but don't crash
                print(f"  ! could not create composite unique index: {e}")


def init():
    print(f"Connecting to: {DATABASE_URL}")
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("All tables created (or already exist):")
    for table in Base.metadata.tables:
        print(f"  - {table}")

    _ensure_target_price_column()
    _ensure_portfolio_columns()

    # Seed initial Bayesian weights (no-op if rows already exist)
    from backend.learning.bayesian import seed_initial_weights
    db = SessionLocal()
    try:
        seed_initial_weights(db)
        print("\nBayesian weights seeded (skipped if already present).")
    finally:
        db.close()


if __name__ == "__main__":
    init()
