from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.function import VERSION_PATTERN

class ApiKeyCreate(BaseModel):
    label: str = Field("default", min_length=1, max_length=64)
    version_tag: Optional[str] = Field(None, pattern=VERSION_PATTERN, description="Pin the key to one version (default: latest)")

class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key_prefix: str
    label: str
    version_tag: Optional[str] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked: bool

class ApiKeyCreated(ApiKeyOut):
    api_key: str = Field(..., description="The full key. Shown only once - store it now.")
    endpoint: str = Field(..., description="Path to POST to, relative to the platform origin")
