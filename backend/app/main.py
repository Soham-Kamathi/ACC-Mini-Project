from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.db import init_db
from backend.app.services.controller import faas_controller
from backend.app.api.auth import router as auth_router
from backend.app.api.functions import router as functions_router
from backend.app.api.invoke import router as invoke_router, public_router as public_invoke_router
from backend.app.api.keys import router as keys_router
from backend.app.api.logs import router as logs_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.cluster import router as cluster_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database & Start Scale-to-Zero Daemon
    import concurrent.futures
    import asyncio
    loop = asyncio.get_running_loop()
    loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=200))
    print("[Startup] Initializing Database...")
    init_db()
    print("[Startup] Starting FaaS Controller Background Reaper...")
    await faas_controller.start()
    yield
    # Shutdown: Stop Reaper
    print("[Shutdown] Stopping FaaS Controller...")
    await faas_controller.stop()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Kubernetes-Based Docker Serverless Function Execution Platform API",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def limit_invoke_payload(request: Request, call_next):
    """Rejects oversized invocation bodies up front (checked on Content-Length)."""
    path = request.url.path
    if request.method == "POST" and (path.startswith(f"{settings.API_V1_STR}/invoke/") or path.startswith(f"{settings.API_V1_STR}/f/")):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.MAX_PAYLOAD_BYTES:
            return JSONResponse(status_code=413, content={"detail": f"Payload exceeds {settings.MAX_PAYLOAD_BYTES} bytes"})
    return await call_next(request)

# Mount API Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(functions_router, prefix=settings.API_V1_STR)
app.include_router(invoke_router, prefix=settings.API_V1_STR)
app.include_router(public_invoke_router, prefix=settings.API_V1_STR)
app.include_router(keys_router, prefix=settings.API_V1_STR)
app.include_router(logs_router, prefix=settings.API_V1_STR)
app.include_router(metrics_router, prefix=settings.API_V1_STR)
app.include_router(cluster_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "platform": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "api_v1": settings.API_V1_STR,
        "status": "online"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
