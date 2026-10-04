"""
Request-driven autoscaler.

Demand signal: the number of requests in flight for a function version (including requests that are
waiting on a cold start). Every AUTOSCALE_INTERVAL_SECONDS the controller calls tick(), which sizes each
tracked version's Deployment as

    desired = ceil(in_flight / target_concurrency), clamped to [max(min_replicas, 1), max_replicas]

- Scale UP is immediate and uses the peak in-flight count seen since the previous tick, so a burst that
  starts and finishes between two ticks is still noticed.
- Scale DOWN is damped: it only goes as low as the highest demand seen over the last
  SCALE_DOWN_STABILIZATION_SECONDS, so short lulls do not make Pods flap.
- Going to zero is not decided here. The idle reaper (controller.py) does that once a function has had
  no traffic for IDLE_TIMEOUT_SECONDS, unless min_replicas > 0.
"""
import asyncio
import math
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Set, Tuple
from prometheus_client import Counter, Gauge
from backend.app.core.config import settings
from backend.app.core.db import SessionLocal
from backend.app.models.function import Function
from backend.app.services.k8s_client import k8s_service

SCALE_EVENTS = Counter(
    "faas_scale_events_total",
    "Autoscaler scale operations",
    ["function_name", "direction"]
)
INFLIGHT_REQUESTS = Gauge(
    "faas_inflight_peak_requests",
    "Peak requests in flight seen by the autoscaler in its last interval (summed over a function's versions)",
    ["function_name"]
)
DESIRED_REPLICAS = Gauge(
    "faas_desired_replicas",
    "Replicas the autoscaler last requested for a function (summed over its versions)",
    ["function_name"]
)

@dataclass
class _State:
    function_id: int
    current: Optional[int] = None  # replicas we last set; None = read from Kubernetes on the next tick
    history: Deque[Tuple[float, int]] = field(default_factory=deque)  # (time, peak in-flight) per tick

class Autoscaler:
    def __init__(self):
        self._inflight: Dict[str, int] = {}
        self._peak: Dict[str, int] = {}
        self._state: Dict[str, _State] = {}
        self._last_peak: Dict[str, int] = {}  # per resource, the demand used at the last tick (for observability)

    # ---- called from the request path (event-loop thread only, so plain ints are safe) ----

    def track(self, function_id: int, resource: str, current: Optional[int] = None):
        """Start (or keep) managing a version's Deployment. `current` is the replica count just set, if known."""
        st = self._state.get(resource)
        if st is None:
            self._state[resource] = _State(function_id=function_id, current=current)
        elif current is not None:
            st.current = current

    @contextmanager
    def in_flight(self, resource: str):
        n = self._inflight.get(resource, 0) + 1
        self._inflight[resource] = n
        if n > self._peak.get(resource, 0):
            self._peak[resource] = n
        try:
            yield
        finally:
            left = self._inflight.get(resource, 1) - 1
            if left <= 0:
                self._inflight.pop(resource, None)
            else:
                self._inflight[resource] = left

    def forget_function(self, function_id: int):
        """Stop managing every version of a function (it was scaled to zero or deleted)."""
        for resource in [r for r, st in self._state.items() if st.function_id == function_id]:
            self._state.pop(resource, None)
            self._peak.pop(resource, None)

    def tracked_resources(self, function_id: int) -> Set[str]:
        return {r for r, st in self._state.items() if st.function_id == function_id}

    def last_peak(self, function_id: int) -> int:
        """Demand (peak in-flight requests) seen at the last tick, summed over the function's versions."""
        return sum(self._last_peak.get(r, 0) for r in self.tracked_resources(function_id))

    # ---- called from the controller loop ----

    @staticmethod
    def _desired(demand: int, target: int, floor: int, cap: int) -> int:
        return max(floor, min(cap, math.ceil(demand / max(target, 1))))

    @staticmethod
    def _load_functions(function_ids) -> Dict[int, Tuple[str, int, int, int]]:
        with SessionLocal() as db:
            rows = db.query(Function).filter(Function.id.in_(function_ids)).all()
            return {f.id: (f.name, f.min_replicas or 0, f.max_replicas or 1, f.target_concurrency or 1) for f in rows}

    @staticmethod
    def _sync_replicas(totals: Dict[int, int]):
        """Mirror the replica count into the DB so the dashboard shows it."""
        with SessionLocal() as db:
            for fn_id, total in totals.items():
                fn = db.query(Function).filter(Function.id == fn_id).first()
                if fn and fn.active_replicas != total:
                    fn.active_replicas = total
            db.commit()

    async def tick(self, now: Optional[float] = None):
        now = time.monotonic() if now is None else now
        if not self._state:
            return
        fns = await asyncio.to_thread(self._load_functions, {st.function_id for st in self._state.values()})

        changed: Set[int] = set()
        for resource, st in list(self._state.items()):
            meta = fns.get(st.function_id)
            if meta is None:  # function deleted
                self._state.pop(resource, None)
                continue
            name, min_replicas, max_replicas, target = meta

            if st.current is None:
                st.current = await asyncio.to_thread(k8s_service.get_replicas, resource)
                if st.current is None:  # no Deployment (e.g. running without Kubernetes)
                    self._state.pop(resource, None)
                    continue

            peak = max(self._peak.pop(resource, 0), self._inflight.get(resource, 0))
            self._last_peak[resource] = peak
            INFLIGHT_REQUESTS.labels(function_name=name).set(self.last_peak(st.function_id))
            st.history.append((now, peak))
            while st.history and now - st.history[0][0] > settings.SCALE_DOWN_STABILIZATION_SECONDS:
                st.history.popleft()

            floor = max(min_replicas, 1)
            cap = max(max_replicas, floor)
            up = self._desired(peak, target, floor, cap)
            down = self._desired(max(p for _, p in st.history), target, floor, cap)

            if up > st.current:
                new = up
            elif down < st.current:
                new = down
            else:
                continue

            direction = "up" if new > st.current else "down"
            print(f"[Autoscaler] {resource}: {st.current} -> {new} replicas (peak in-flight={peak}, target={target})")
            if await asyncio.to_thread(k8s_service.scale_deployment, resource, new):
                st.current = new
                SCALE_EVENTS.labels(function_name=name, direction=direction).inc()
                changed.add(st.function_id)

        if changed:
            totals = {fid: sum(s.current or 0 for s in self._state.values() if s.function_id == fid) for fid in changed}
            await asyncio.to_thread(self._sync_replicas, totals)
            for fid, total in totals.items():
                if fid in fns:
                    DESIRED_REPLICAS.labels(function_name=fns[fid][0]).set(total)

autoscaler = Autoscaler()
