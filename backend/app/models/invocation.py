from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from backend.app.core.db import Base

class InvocationLog(Base):
    __tablename__ = "invocation_logs"

    id = Column(Integer, primary_key=True, index=True)
    function_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("function_versions.id"), nullable=True)
    request_id = Column(String(64), index=True, nullable=False)
    
    is_cold_start = Column(Boolean, default=False)
    cold_start_duration_ms = Column(Float, default=0.0)
    execution_duration_ms = Column(Float, default=0.0)
    total_duration_ms = Column(Float, default=0.0)
    
    status_code = Column(Integer, default=200)
    payload_input = Column(Text, default="")
    payload_output = Column(Text, default="")
    error_message = Column(Text, default="")
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    function = relationship("Function", back_populates="invocations")
