from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import settings

# Setup database engine
if settings.DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # Ensure all models are imported before creating tables
    import backend.app.models
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()

def _add_missing_columns():
    """create_all never alters existing tables; add columns introduced after a DB was first created."""
    from sqlalchemy import inspect, text
    additions = [
        ("invocation_logs", "executed_on", "VARCHAR(16) DEFAULT 'unknown'"),
        ("functions", "public_id", "VARCHAR(32)"),
    ]
    insp = inspect(engine)
    for table, column, ddl in additions:
        if table in insp.get_table_names() and column not in {c["name"] for c in insp.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    # functions created before public ids existed: backfill, then enforce uniqueness
    import uuid
    with engine.begin() as conn:
        for (fn_id,) in conn.execute(text("SELECT id FROM functions WHERE public_id IS NULL")).fetchall():
            conn.execute(text("UPDATE functions SET public_id = :p WHERE id = :i"), {"p": uuid.uuid4().hex[:16], "i": fn_id})
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_functions_public_id ON functions (public_id)"))

# Auto-initialize database tables
init_db()
