from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.core.db import get_db
from backend.app.core.security import get_current_user_id
from backend.app.models.function import Function
from backend.app.models.invocation import InvocationLog
from backend.app.schemas.invocation import InvocationLogOut

router = APIRouter(tags=["Logs & Metrics"])

@router.get("/functions/{name}/logs", response_model=List[InvocationLogOut])
def get_function_logs(
    name: str,
    limit: int = Query(50, ge=1, le=500),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    fn = db.query(Function).filter(Function.name == name, Function.owner_id == user_id).first()
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")

    logs = db.query(InvocationLog).filter(
        InvocationLog.function_id == fn.id
    ).order_by(InvocationLog.timestamp.desc()).limit(limit).all()

    return [InvocationLogOut.model_validate(log) for log in logs]

@router.get("/logs/recent", response_model=List[InvocationLogOut])
def get_recent_logs(
    limit: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # Join with user's functions
    logs = db.query(InvocationLog).join(Function).filter(
        Function.owner_id == user_id
    ).order_by(InvocationLog.timestamp.desc()).limit(limit).all()

    return [InvocationLogOut.model_validate(log) for log in logs]
