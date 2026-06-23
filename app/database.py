import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Compute BASE_DIR once at module level (always available)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Get database URL from environment, or fallback to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # local SQLite (for testing)
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'oilspill.db')}"
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, echo=True
    )
else:
    # Postgres (Neon) – use sync driver
    engine = create_engine(DATABASE_URL, echo=True, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session (used in main.py)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()