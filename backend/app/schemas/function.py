from pydantic import BaseModel, Field, ConfigDict
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

class FunctionUpdate(BaseModel):
    description: Optional[str] = None
    code: Optional[str] = None
    requirements: Optional[str] = None
    memory_limit: Optional[str] = None
    cpu_limit: Optional[str] = None
    timeout_seconds: Optional[int] = None
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
    last_invoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class FunctionDetailOut(FunctionOut):
    versions: List[FunctionVersionOut] = []
