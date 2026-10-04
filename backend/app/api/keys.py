from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.api_keys import generate_api_key, hash_api_key
from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.core.security import get_current_user_id
from backend.app.models.api_key import ApiKey
from backend.app.models.function import Function, FunctionVersion
from backend.app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/functions/{name}/keys", tags=["API Keys"])

def _owned_function(db: Session, user_id: int, name: str) -> Function:
    fn = db.query(Function).filter(Function.name == name, Function.owner_id == user_id).first()
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")
    return fn

def _owned_key(db: Session, fn: Function, key_id: int) -> ApiKey:
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.function_id == fn.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")
    return key

def _issue(db: Session, fn: Function, label: str, version_tag) -> ApiKeyCreated:
    plaintext = generate_api_key()
    key = ApiKey(
        function_id=fn.id,
        key_hash=hash_api_key(plaintext),
        key_prefix=plaintext[:10],
        label=label,
        version_tag=version_tag,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyCreated(
        **ApiKeyOut.model_validate(key).model_dump(),
        api_key=plaintext,
        endpoint=f"{settings.API_V1_STR}/f/{fn.public_id}",
    )

@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_key(name: str, body: ApiKeyCreate, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    fn = _owned_function(db, user_id, name)
    active = db.query(ApiKey).filter(ApiKey.function_id == fn.id, ApiKey.revoked.is_(False)).count()
    if active >= settings.MAX_API_KEYS_PER_FUNCTION:
        raise HTTPException(status_code=400, detail=f"At most {settings.MAX_API_KEYS_PER_FUNCTION} active keys per function; revoke one first.")
    if body.version_tag:
        exists = db.query(FunctionVersion).filter(
            FunctionVersion.function_id == fn.id, FunctionVersion.version_tag == body.version_tag).first()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Version '{body.version_tag}' not found for function '{name}'.")
    return _issue(db, fn, body.label, body.version_tag)

@router.get("", response_model=List[ApiKeyOut])
def list_keys(name: str, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    fn = _owned_function(db, user_id, name)
    return db.query(ApiKey).filter(ApiKey.function_id == fn.id).order_by(ApiKey.id.desc()).all()

@router.post("/{key_id}/rotate", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def rotate_key(name: str, key_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Issues a replacement key with the same label/version pin and revokes the old one."""
    fn = _owned_function(db, user_id, name)
    old = _owned_key(db, fn, key_id)
    if old.revoked:
        raise HTTPException(status_code=400, detail="Key is already revoked.")
    old.revoked = True
    db.commit()
    return _issue(db, fn, old.label, old.version_tag)

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(name: str, key_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    fn = _owned_function(db, user_id, name)
    key = _owned_key(db, fn, key_id)
    key.revoked = True
    db.commit()
    return None
