from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List

class FunctionCreate(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9-]+$", description="Lowercase letters, numbers, and dashes only")
    runtime: str = "python311"
    description: Optional[str] = ""
    code: str = Field(..., description="Python source code containing `def handler(event):`")
    requirements: Optional[str] = ""
    memory_limit: Optional[str] = "256Mi"
    cpu_limit: Optional[str] = "500m"
    timeout_seconds: Optional[int] = 10

class FunctionUpdate(BaseModel):
    description: Optional[str] = None
    code: Optional[str] = None
    requirements: Optional[str] = None
    memory_limit: Optional[str] = None
    cpu_limit: Optional[str] = None
    timeout_seconds: Optional[int] = None
    version_tag: Optional[str] = None

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
    owner_id: int
    runtime: str
    description: Optional[str] = ""
    status: str
    status_message: Optional[str] = ""
    memory_limit: str
    cpu_limit: str
    timeout_seconds: int
    active_replicas: int
    last_invoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class FunctionDetailOut(FunctionOut):
    versions: List[FunctionVersionOut] = []
