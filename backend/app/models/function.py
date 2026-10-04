import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.app.core.db import Base

class Function(Base):
    __tablename__ = "functions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), index=True, nullable=False)
    # Stable, unguessable id used in the public endpoint /api/v1/f/{public_id}
    public_id = Column(String(32), unique=True, index=True, nullable=False, default=lambda: uuid.uuid4().hex[:16])
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    runtime = Column(String(32), default="python311", nullable=False)
    description = Column(String(256), default="")
    
    # Status: CREATING, BUILDING, READY, RUNNING, IDLE, SCALED_TO_ZERO, ERROR
    status = Column(String(32), default="CREATING", nullable=False)
    status_message = Column(Text, default="")
    
    # Resource Constraints
    memory_limit = Column(String(32), default="256Mi")
    cpu_limit = Column(String(32), default="500m")
    timeout_seconds = Column(Integer, default=10)
    
    active_replicas = Column(Integer, default=0)
    last_invoked_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="functions")
    versions = relationship("FunctionVersion", back_populates="function", cascade="all, delete-orphan")
    invocations = relationship("InvocationLog", back_populates="function", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="function", cascade="all, delete-orphan")

class FunctionVersion(Base):
    __tablename__ = "function_versions"

    id = Column(Integer, primary_key=True, index=True)
    function_id = Column(Integer, ForeignKey("functions.id"), nullable=False)
    version_tag = Column(String(32), default="v1", nullable=False)
    code = Column(Text, nullable=False)
    requirements = Column(Text, default="")
    image_tag = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    function = relationship("Function", back_populates="versions")
