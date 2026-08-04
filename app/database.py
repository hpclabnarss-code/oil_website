import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.models import SpillRecord

# Compute BASE_DIR once at module level (always available)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Get database URL from environment, or fallback to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # local SQLite (for testing)
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'oilspill.db')}"
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
    )
else:
    # Neon/Heroku-style URLs start with "postgres://", but SQLAlchemy 1.4+
    # requires the "postgresql://" scheme
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session (used in main.py)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_updated(engine):
    """
    Automatically add any missing columns to the spill_records table.
    This ensures the live schema matches the model without manual SQL.
    """
    inspector = inspect(engine)
    table_name = SpillRecord.__tablename__
    if table_name not in inspector.get_table_names():
        # Table doesn't exist yet; create_all() will handle it.
        return

    existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
    model_columns = {c.name for c in SpillRecord.__table__.columns}

    missing = model_columns - existing_columns
    if not missing:
        return

    with engine.connect() as conn:
        for col_name in missing:
            column = SpillRecord.__table__.columns[col_name]
            col_type = column.type.compile(engine.dialect)
            # Build ALTER TABLE statement (Postgres & SQLite compatible)
            alter_stmt = f'ALTER TABLE {table_name} ADD COLUMN "{col_name}" {col_type}'
            conn.execute(text(alter_stmt))
            conn.commit()