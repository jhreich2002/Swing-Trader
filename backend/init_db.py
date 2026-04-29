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


def init():
    print(f"Connecting to: {DATABASE_URL}")
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("All tables created (or already exist):")
    for table in Base.metadata.tables:
        print(f"  - {table}")

    _ensure_target_price_column()

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
