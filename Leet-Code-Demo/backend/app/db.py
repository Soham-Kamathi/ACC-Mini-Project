from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    problem_id = Column(String(80), nullable=False, index=True)
    code = Column(Text, nullable=False)
    verdict = Column(String(40), nullable=False)
    passed = Column(Integer, default=0)
    total = Column(Integer, default=0)
    execution_time_ms = Column(Float, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    results_json = Column(Text, default="[]")

def init_db():
    Base.metadata.create_all(engine)

