"""
Run this once to create all database tables and seed initial Bayesian weights.
Safe to re-run — uses checkfirst=True so existing tables are not dropped,
and seed_initial_weights() skips regimes that already have weight rows.
"""
from backend.database import Base, engine, SessionLocal
from backend.config import DATABASE_URL


def init():
    print(f"Connecting to: {DATABASE_URL}")
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("All tables created (or already exist):")
    for table in Base.metadata.tables:
        print(f"  - {table}")

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
