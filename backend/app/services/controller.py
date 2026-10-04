import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.db import SessionLocal
from backend.app.models.function import Function
from backend.app.services.k8s_client import k8s_service
from backend.app.services.naming import function_key
from backend.app.services.router import mark_cold
from backend.app.services.autoscaler import autoscaler

class FaasController:
    def __init__(self):
        self.is_running = False
        self._task: asyncio.Task = None
        self._autoscale_task: asyncio.Task = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._reaper_loop())
        self._autoscale_task = asyncio.create_task(self._autoscale_loop())
        print("[FaasController] Scale-to-zero reaper and autoscaler daemons started.")

    async def stop(self):
        self.is_running = False
        for task in (self._task, self._autoscale_task):
            if task:
                task.cancel()
        print("[FaasController] Scale-to-zero reaper daemon stopped.")

    async def _reaper_loop(self):
        while self.is_running:
            try:
                await self.check_idle_functions()
            except Exception as e:
                print(f"[FaasController Error] Reaper cycle error: {e}")
            await asyncio.sleep(settings.REAPER_INTERVAL_SECONDS)

    async def _autoscale_loop(self):
        while self.is_running:
            try:
                await autoscaler.tick()
            except Exception as e:
                print(f"[FaasController Error] Autoscaler cycle error: {e}")
            await asyncio.sleep(settings.AUTOSCALE_INTERVAL_SECONDS)

    async def check_idle_functions(self):
        """
        Scans all running or idle functions. If idle time exceeds threshold, scale replicas to 0.
        """
        db: Session = SessionLocal()
        try:
            now = datetime.utcnow()
            threshold = now - timedelta(seconds=settings.IDLE_TIMEOUT_SECONDS)

            # Query functions that have replicas > 0 and are idle past threshold
            active_functions = db.query(Function).filter(
                Function.active_replicas > 0,
                Function.status.in_(["RUNNING", "IDLE", "READY"])
            ).all()

            for fn in active_functions:
                if (fn.min_replicas or 0) > 0:
                    continue  # a minimum replica count means this function is never scaled to zero
                last_activity = fn.last_invoked_at or fn.created_at
                if last_activity < threshold:
                    print(f"[FaasController] Function '{fn.name}' idle for >{settings.IDLE_TIMEOUT_SECONDS}s. Scaling to 0...")
                    # Stop autoscaling first so it cannot bring the Pods back while they are being removed
                    autoscaler.forget_function(fn.id)
                    # Scales every version's Deployment; None means there is nothing deployed to scale
                    scaled = k8s_service.scale_function(function_key(fn.owner_id, fn.name), 0)

                    if scaled is not False:
                        mark_cold(fn.id)
                        fn.active_replicas = 0
                        fn.status = "SCALED_TO_ZERO"
                        fn.status_message = f"Scaled to 0 replicas due to inactivity (idle > {settings.IDLE_TIMEOUT_SECONDS}s)"
                        db.commit()
                        print(f"[FaasController] Function '{fn.name}' is now SCALED_TO_ZERO.")
        finally:
            db.close()

faas_controller = FaasController()
