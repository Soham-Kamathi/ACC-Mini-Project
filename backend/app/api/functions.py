from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from backend.app.core.db import get_db
from backend.app.core.security import get_current_user_id
from backend.app.models.user import User
from backend.app.models.function import Function, FunctionVersion
from backend.app.schemas.function import FunctionCreate, FunctionUpdate, FunctionOut, FunctionDetailOut
from backend.app.services.builder import builder_service
from backend.app.services.k8s_client import k8s_service
from backend.app.api.invoke import invalidate_fn_cache
from backend.app.services.router import invalidate_router_cache

router = APIRouter(prefix="/functions", tags=["Functions"])

def _build_and_deploy_task(function_id: int, username: str, function_name: str, version_tag: str, code: str, requirements: str, runtime: str, memory_limit: str, cpu_limit: str):
    """Background task for image build and Kubernetes deployment."""
    from backend.app.core.db import SessionLocal
    db = SessionLocal()
    try:
        fn = db.query(Function).filter(Function.id == function_id).first()
        if not fn:
            return
        
        fn.status = "BUILDING"
        fn.status_message = "Building container image..."
        db.commit()

        # 1. Build image
        image_tag = builder_service.build_function_image(
            username=username,
            function_name=function_name,
            version_tag=version_tag,
            code=code,
            requirements=requirements,
            runtime=runtime
        )

        # 2. Deploy to Kubernetes
        k8s_service.deploy_function(
            function_name=function_name,
            image_tag=image_tag,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
            initial_replicas=1
        )

        fn.status = "READY"
        fn.active_replicas = 1
        fn.status_message = "Function is deployed and ready for invocations."
        db.commit()
    except Exception as e:
        print(f"[Build Error] Failed to build/deploy {function_name}: {e}")
        fn = db.query(Function).filter(Function.id == function_id).first()
        if fn:
            fn.status = "ERROR"
            fn.status_message = f"Build/Deploy failed: {str(e)}"
            db.commit()
    finally:
        db.close()

@router.post("/", response_model=FunctionOut, status_code=status.HTTP_201_CREATED)
def create_function(
    func_in: FunctionCreate, 
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check for name conflict for this user
    existing = db.query(Function).filter(
        Function.name == func_in.name,
        Function.owner_id == user_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Function with name '{func_in.name}' already exists.")

    new_fn = Function(
        name=func_in.name,
        owner_id=user_id,
        runtime=func_in.runtime,
        description=func_in.description or "",
        status="CREATING",
        status_message="Initializing build...",
        memory_limit=func_in.memory_limit or "256Mi",
        cpu_limit=func_in.cpu_limit or "500m",
        timeout_seconds=func_in.timeout_seconds or 10,
        active_replicas=0
    )
    db.add(new_fn)
    db.commit()
    db.refresh(new_fn)

    # Initial Version
    version_tag = "v1"
    image_tag = f"localhost:5000/{user.username}/{new_fn.name}:{version_tag}"
    new_version = FunctionVersion(
        function_id=new_fn.id,
        version_tag=version_tag,
        code=func_in.code,
        requirements=func_in.requirements or "",
        image_tag=image_tag,
        is_active=True
    )
    db.add(new_version)
    db.commit()

    # Trigger async build and deploy in background
    background_tasks.add_task(
        _build_and_deploy_task,
        function_id=new_fn.id,
        username=user.username,
        function_name=new_fn.name,
        version_tag=version_tag,
        code=func_in.code,
        requirements=func_in.requirements or "",
        runtime=new_fn.runtime,
        memory_limit=new_fn.memory_limit,
        cpu_limit=new_fn.cpu_limit
    )

    invalidate_fn_cache(new_fn.name)
    invalidate_router_cache(new_fn.id)

    return FunctionOut.model_validate(new_fn)

@router.get("/", response_model=List[FunctionOut])
def list_functions(
    user_id: int = Depends(get_current_user_id), 
    db: Session = Depends(get_db)
):
    functions = db.query(Function).filter(Function.owner_id == user_id).all()
    return [FunctionOut.model_validate(fn) for fn in functions]

@router.get("/{name}", response_model=FunctionDetailOut)
def get_function(
    name: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    fn = db.query(Function).filter(
        Function.name == name,
        Function.owner_id == user_id
    ).first()
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")
    return FunctionDetailOut.model_validate(fn)

@router.put("/{name}", response_model=FunctionDetailOut)
def update_function(
    name: str,
    func_update: FunctionUpdate,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    fn = db.query(Function).filter(Function.name == name, Function.owner_id == user_id).first()
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")

    if func_update.description is not None:
        fn.description = func_update.description
    if func_update.memory_limit is not None:
        fn.memory_limit = func_update.memory_limit
    if func_update.cpu_limit is not None:
        fn.cpu_limit = func_update.cpu_limit
    if func_update.timeout_seconds is not None:
        fn.timeout_seconds = func_update.timeout_seconds

    # If code changed, create a new version
    if func_update.code is not None:
        latest_version = db.query(FunctionVersion).filter(FunctionVersion.function_id == fn.id).count()
        new_version_tag = func_update.version_tag or f"v{latest_version + 1}"
        image_tag = f"localhost:5000/{user.username}/{fn.name}:{new_version_tag}"

        new_version = FunctionVersion(
            function_id=fn.id,
            version_tag=new_version_tag,
            code=func_update.code,
            requirements=func_update.requirements or "",
            image_tag=image_tag,
            is_active=True
        )
        db.add(new_version)
        db.commit()

        background_tasks.add_task(
            _build_and_deploy_task,
            function_id=fn.id,
            username=user.username,
            function_name=fn.name,
            version_tag=new_version_tag,
            code=func_update.code,
            requirements=func_update.requirements or "",
            runtime=fn.runtime,
            memory_limit=fn.memory_limit,
            cpu_limit=fn.cpu_limit
        )

    db.commit()
    db.refresh(fn)

    invalidate_fn_cache(fn.name)
    invalidate_router_cache(fn.id)

    return FunctionDetailOut.model_validate(fn)

@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_function(
    name: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    fn = db.query(Function).filter(Function.name == name, Function.owner_id == user_id).first()
    if not fn:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")

    # 1. Clean up Kubernetes deployment & service
    k8s_service.delete_function(name)

    invalidate_fn_cache(name)
    invalidate_router_cache(fn.id)

    # 2. Delete database records
    db.delete(fn)
    db.commit()
    return None
