from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Any, Dict

class InvokeRequest(BaseModel):
    payload: Optional[Dict[str, Any]] = {}
    async_mode: Optional[bool] = False

class InvokeResponse(BaseModel):
    request_id: str
    function_name: str
    version: str
    status_code: int
    is_cold_start: bool
    cold_start_duration_ms: float
    execution_duration_ms: float
    total_duration_ms: float
    result: Optional[Any] = None
    error: Optional[str] = None

class InvocationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    is_cold_start: bool
    cold_start_duration_ms: float
    execution_duration_ms: float
    total_duration_ms: float
    status_code: int
    payload_input: Optional[str] = ""
    payload_output: Optional[str] = ""
    error_message: Optional[str] = ""
    timestamp: datetime
