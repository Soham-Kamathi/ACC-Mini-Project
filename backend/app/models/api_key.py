from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.app.core.db import Base

class ApiKey(Base):
    """
    A credential scoped to exactly one function. Only the SHA-256 hash is stored; the plaintext key
    is shown to the owner once, when it is created.
    """
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    function_id = Column(Integer, ForeignKey("functions.id"), index=True, nullable=False)
    key_hash = Column(String(64), unique=True, index=True, nullable=False)
    key_prefix = Column(String(16), nullable=False)  # first characters, so owners can tell keys apart
    label = Column(String(64), default="default")
    version_tag = Column(String(32), nullable=True)  # if set, the key can only invoke this version
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False, nullable=False)

    function = relationship("Function", back_populates="api_keys")
