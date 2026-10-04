import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from sqlalchemy.orm import Session
from backend.app.core.api_keys import KEY_PREFIX, hash_api_key, rate_limiter
from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.core.security import decode_user_id
from backend.app.models.api_key import ApiKey
from backend.app.models.function import Function
from backend.app.schemas.invocation import InvokeResponse
from backend.app.services.router import router_service, VersionNotFound, VersionNotReady

# Owner-facing routes (by function name) and the public route (by stable public id).
# Both accept either the owner's JWT or an API key scoped to the function.
router = APIRouter(prefix="/invoke", tags=["Invocation"])
public_router = APIRouter(prefix="/f", tags=["Invocation (public endpoint)"])

# Function names are only unique per owner, so everything is looked up by (owner_id, name).
_fn_cache: Dict[Tuple[int, str], Tuple[Function, float]] = {}

def invalidate_fn_cache(owner_id: Optional[int] = None, name: Optional[str] = None):
    if owner_id is not None and name is not None:
        _fn_cache.pop((owner_id, name), None)
    else:
        _fn_cache.clear()

def get_cached_function(db: Session, owner_id: int, name: str) -> Optional[Function]:
    now_time = time.time()
    key = (owner_id, name)
    if key in _fn_cache:
        fn, ts = _fn_cache[key]
        if (now_time - ts) < 15.0:
            return fn
    fn = db.query(Function).filter(Function.name == name, Function.owner_id == owner_id).first()
    if fn:
        _fn_cache[key] = (fn, now_time)
    return fn

def _normalize_payload(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    return {"value": payload, "input": payload, "raw": payload}

@dataclass
class Caller:
    """Who is invoking: the owner (JWT) or the holder of a function-scoped API key."""
    user_id: Optional[int] = None
    api_key: Optional[ApiKey] = None

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}
_LAST_USED_GRANULARITY = timedelta(seconds=60)

def get_caller(request: Request, db: Session = Depends(get_db)) -> Caller:
    api_key = request.headers.get("x-api-key")
    auth = request.headers.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    if not api_key and bearer and bearer.startswith(KEY_PREFIX):
        api_key, bearer = bearer, None

    if api_key:
        row = db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(api_key), ApiKey.revoked.is_(False)).first()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key", headers=_UNAUTHORIZED)
        wait = rate_limiter.check(row.id, settings.API_KEY_RATE_LIMIT_PER_MINUTE)
        if wait > 0:
            raise HTTPException(status_code=429, detail="Rate limit exceeded for this API key",
                                headers={"Retry-After": str(int(wait) + 1)})
        # last_used_at is only written about once a minute to avoid a DB write per call
        now = datetime.utcnow()
        if row.last_used_at is None or now - row.last_used_at > _LAST_USED_GRANULARITY:
            row.last_used_at = now
            db.commit()
        return Caller(api_key=row)

    if bearer:
        return Caller(user_id=decode_user_id(bearer))
    raise HTTPException(status_code=401, detail="Provide a Bearer token or an X-API-Key header", headers=_UNAUTHORIZED)

async def _run(db: Session, fn: Function, caller: Caller, version: Optional[str], payload: Any) -> InvokeResponse:
    pinned = caller.api_key.version_tag if caller.api_key else None
    if pinned:
        if version and version != pinned:
            raise HTTPException(status_code=403, detail=f"This API key is pinned to version '{pinned}'")
        version = pinned
    try:
        result = await router_service.invoke_function(
            db=db, function=fn, version_tag=version, payload=_normalize_payload(payload)
        )
        return InvokeResponse(**result)
    except VersionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except VersionNotReady as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def _invoke_by_name(db: Session, caller: Caller, name: str, version: Optional[str], payload: Any) -> InvokeResponse:
    if caller.api_key:
        fn = caller.api_key.function
        if fn.name != name:
            # 404 rather than 403 so a key cannot be used to probe which other functions exist
            raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")
    else:
        fn = get_cached_function(db, caller.user_id, name)
        if not fn:
            raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")
    return await _run(db, fn, caller, version, payload)

async def _invoke_by_public_id(db: Session, caller: Caller, public_id: str, version: Optional[str], payload: Any) -> InvokeResponse:
    fn = db.query(Function).filter(Function.public_id == public_id).first()
    allowed = fn is not None and (
        (caller.api_key is not None and caller.api_key.function_id == fn.id)
        or (caller.user_id is not None and fn.owner_id == caller.user_id)
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Function not found.")
    return await _run(db, fn, caller, version, payload)

@router.post("/{name}", response_model=InvokeResponse)
async def invoke_latest(name: str, payload: Any = Body(default={}),
                        caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return await _invoke_by_name(db, caller, name, None, payload)

@router.post("/{name}/{version}", response_model=InvokeResponse)
async def invoke_version(name: str, version: str, payload: Any = Body(default={}),
                         caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return await _invoke_by_name(db, caller, name, version, payload)

@public_router.post("/{public_id}", response_model=InvokeResponse)
async def invoke_public_latest(public_id: str, payload: Any = Body(default={}),
                               caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return await _invoke_by_public_id(db, caller, public_id, None, payload)

@public_router.post("/{public_id}/{version}", response_model=InvokeResponse)
async def invoke_public_version(public_id: str, version: str, payload: Any = Body(default={}),
                                caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return await _invoke_by_public_id(db, caller, public_id, version, payload)
