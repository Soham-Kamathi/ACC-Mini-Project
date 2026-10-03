import time
from typing import Optional, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.app.core.db import get_db
from backend.app.models.function import Function
from backend.app.schemas.invocation import InvokeResponse
from backend.app.services.router import router_service

router = APIRouter(prefix="/invoke", tags=["Invocation"])

_fn_cache: Dict[str, Tuple[Function, float]] = {}

def invalidate_fn_cache(name: Optional[str] = None):
    global _fn_cache
    if name:
        _fn_cache.pop(name, None)
    else:
        _fn_cache.clear()

def get_cached_function(db: Session, name: str) -> Optional[Function]:
    now_time = time.time()
    if name in _fn_cache:
        fn, ts = _fn_cache[name]
        if (now_time - ts) < 15.0:
            return fn
    fn = db.query(Function).filter(Function.name == name).order_by(Function.id.desc()).first()
    if fn:
        _fn_cache[name] = (fn, now_time)
    return fn

def _normalize_payload(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    return {"value": payload, "input": payload, "raw": payload}

@router.post("/{name}", response_model=InvokeResponse)
async def invoke_latest(
    name: str,
    payload: Any = Body(default={}),
    db: Session = Depends(get_db)
):
    fn = get_cached_function(db, name)
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")

    normalized_payload = _normalize_payload(payload)
    try:
        result = await router_service.invoke_function(db=db, function=fn, payload=normalized_payload)
        return InvokeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{name}/{version}", response_model=InvokeResponse)
async def invoke_version(
    name: str,
    version: str,
    payload: Any = Body(default={}),
    db: Session = Depends(get_db)
):
    fn = db.query(Function).filter(Function.name == name).order_by(Function.id.desc()).first()
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")

    normalized_payload = _normalize_payload(payload)
    try:
        result = await router_service.invoke_function(db=db, function=fn, version_tag=version, payload=normalized_payload)
        return InvokeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

