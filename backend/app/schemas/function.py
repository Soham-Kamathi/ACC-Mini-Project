from pydantic import BaseModel, Field, ConfigDict, model_validator
from backend.app.core.config import settings
from datetime import datetime
from typing import Optional, List

# Names become Kubernetes resource names (fn-<owner>-<name>-<version>), so they must be DNS-1123 labels
# and short enough to keep the full name under 63 characters.
NAME_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?$"
VERSION_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?$"

class FunctionCreate(BaseModel):
    name: str = Field(..., pattern=NAME_PATTERN, description="DNS-1123 label: lowercase letters, digits and dashes, 1-30 chars, starts/ends alphanumeric")
    runtime: str = "python311"
    description: Optional[str] = ""
    code: str = Field(..., description="Python source code containing `def handler(event):`")
    requirements: Optional[str] = ""
    memory_limit: Optional[str] = "256Mi"
    cpu_limit: Optional[str] = "500m"
    timeout_seconds: Optional[int] = 10
    min_replicas: int = Field(settings.DEFAULT_MIN_REPLICAS, ge=0, le=settings.MAX_REPLICAS_LIMIT, description="0 enables scale-to-zero")
    max_replicas: int = Field(settings.DEFAULT_MAX_REPLICAS, ge=1, le=settings.MAX_REPLICAS_LIMIT)
    target_concurrency: int = Field(settings.DEFAULT_TARGET_CONCURRENCY, ge=1, le=100, description="In-flight requests one Pod should handle")

    @model_validator(mode="after")
    def _min_not_above_max(self):
        if self.min_replicas > self.max_replicas:
            raise ValueError("min_replicas must be <= max_replicas")
        return self

class FunctionUpdate(BaseModel):
    description: Optional[str] = None
    code: Optional[str] = None
    requirements: Optional[str] = None
    memory_limit: Optional[str] = None
    cpu_limit: Optional[str] = None
    timeout_seconds: Optional[int] = None
    min_replicas: Optional[int] = Field(None, ge=0, le=settings.MAX_REPLICAS_LIMIT)
    max_replicas: Optional[int] = Field(None, ge=1, le=settings.MAX_REPLICAS_LIMIT)
    target_concurrency: Optional[int] = Field(None, ge=1, le=100)
    version_tag: Optional[str] = Field(None, pattern=VERSION_PATTERN, description="Lowercase DNS-1123 label, max 12 chars")

class FunctionVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_tag: str
    code: str
    requirements: Optional[str] = ""
    image_tag: str
    is_active: bool
    created_at: datetime

class FunctionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    public_id: str
    owner_id: int
    runtime: str
    description: Optional[str] = ""
    status: str
    status_message: Optional[str] = ""
    memory_limit: str
    cpu_limit: str
    timeout_seconds: int
    active_replicas: int
    min_replicas: int = 0
    max_replicas: int = 5
    target_concurrency: int = 5
    last_invoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class FunctionDetailOut(FunctionOut):
    versions: List[FunctionVersionOut] = []
