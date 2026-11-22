#!/usr/bin/env python3
"""
Concurrency and latency benchmark for the Python Code Execution function.

This script sends concurrent code-execution requests to a deployed
"python-code-executor" function via the platform's public invocation endpoint
and reports throughput and latency statistics.

Prerequisites:
  1. The FaaS platform must be running (backend + K8s).
  2. A function named "python-code-executor" must be deployed and READY.
  3. An API key must be generated for that function.

Usage:
    python benchmarks/code_executor_test.py \\
        --base-url http://localhost:8000 \\
        --public-id <public_id> \\
        --api-key <fk_...> \\
        [--concurrency 1,10,50,100] \\
        [--requests-per-level 50]

If --api-key / --public-id are not supplied the script will try to auto-detect
them by logging in with the demo developer account and querying the API.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import httpx
except ImportError:
    print("This benchmark requires httpx.  Install with:  pip install httpx")
    sys.exit(1)


# ── Test Programs ─────────────────────────────────────────────────────────

SIMPLE_PROGRAM = {
    "language": "python",
    "code": "a, b = map(int, input().split())\nprint(a + b)",
    "stdin": "10 20",
    "timeout_seconds": 5,
}

CPU_PROGRAM = {
    "language": "python",
    "code": (
        "n = 30\n"
        "a, b = 0, 1\n"
        "for _ in range(n):\n"
        "    a, b = b, a + b\n"
        "print(a)\n"
    ),
    "stdin": "",
    "timeout_seconds": 5,
}


# ── Result container ──────────────────────────────────────────────────────

@dataclass
class RunResult:
    status_code: int
    exec_status: str  # success / runtime_error / ...
    latency_ms: float
    is_cold_start: bool = False
    error: Optional[str] = None


@dataclass
class LevelReport:
    concurrency: int
    total_requests: int
    successful: int = 0
    failed: int = 0
    cold_starts: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def rps(self) -> float:
        return self.total_requests / self.elapsed_s if self.elapsed_s > 0 else 0

    @property
    def error_rate_pct(self) -> float:
        return (self.failed / self.total_requests * 100) if self.total_requests > 0 else 0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        idx = int(len(s) * p / 100)
        return s[min(idx, len(s) - 1)]

    def summary(self) -> str:
        avg = statistics.mean(self.latencies_ms) if self.latencies_ms else 0
        lines = [
            f"  Concurrency:      {self.concurrency}",
            f"  Total requests:   {self.total_requests}",
            f"  Successful:       {self.successful}",
            f"  Failed:           {self.failed}  ({self.error_rate_pct:.1f}%)",
            f"  Cold starts:      {self.cold_starts}",
            f"  Elapsed:          {self.elapsed_s:.2f}s",
            f"  Throughput:       {self.rps:.1f} req/s",
            f"  Avg latency:      {avg:.1f} ms",
            f"  p50 latency:      {self.percentile(50):.1f} ms",
            f"  p95 latency:      {self.percentile(95):.1f} ms",
            f"  p99 latency:      {self.percentile(99):.1f} ms",
        ]
        return "\n".join(lines)


# ── Worker ────────────────────────────────────────────────────────────────

async def send_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    payload: dict,
) -> RunResult:
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=60)
        latency = (time.perf_counter() - t0) * 1000
        body = resp.json()

        # The gateway wraps the handler result in an InvokeResponse
        inner_result = body.get("result", {})
        exec_status = "unknown"
        if isinstance(inner_result, dict):
            exec_status = inner_result.get("status", "unknown")

        return RunResult(
            status_code=resp.status_code,
            exec_status=exec_status,
            latency_ms=latency,
            is_cold_start=body.get("is_cold_start", False),
            error=body.get("error"),
        )
    except Exception as exc:
        latency = (time.perf_counter() - t0) * 1000
        return RunResult(
            status_code=0,
            exec_status="error",
            latency_ms=latency,
            error=str(exc),
        )


async def run_level(
    url: str,
    headers: dict,
    payload: dict,
    concurrency: int,
    total_requests: int,
) -> LevelReport:
    report = LevelReport(concurrency=concurrency, total_requests=total_requests)
    sem = asyncio.Semaphore(concurrency)

    async def _task(client: httpx.AsyncClient):
        async with sem:
            return await send_request(client, url, headers, payload)

    async with httpx.AsyncClient() as client:
        t0 = time.perf_counter()
        tasks = [asyncio.create_task(_task(client)) for _ in range(total_requests)]
        results = await asyncio.gather(*tasks)
        report.elapsed_s = time.perf_counter() - t0

    for r in results:
        report.latencies_ms.append(r.latency_ms)
        if r.is_cold_start:
            report.cold_starts += 1
        if r.status_code == 200 and r.exec_status == "success":
            report.successful += 1
        else:
            report.failed += 1

    return report


# ── Auto-detection helpers ────────────────────────────────────────────────

def auto_detect(base_url: str):
    """Try to find the python-code-executor function and an API key."""
    import httpx as httpx_sync

    # Login as demo developer
    login_data = {"username": "developer", "password": "Password123!"}
    with httpx_sync.Client(base_url=base_url, timeout=10) as c:
        resp = c.post("/api/v1/auth/login", data=login_data)
        if resp.status_code != 200:
            return None, None
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Find function
        resp = c.get("/api/v1/functions/", headers=headers)
        if resp.status_code != 200:
            return None, None
        funcs = resp.json()
        fn = next((f for f in funcs if "executor" in f["name"] or "code" in f["name"]), None)
        if not fn:
            return None, None
        public_id = fn["public_id"]
        name = fn["name"]

        # Find or create API key
        resp = c.get(f"/api/v1/functions/{name}/keys", headers=headers)
        keys = resp.json() if resp.status_code == 200 else []
        active_keys = [k for k in keys if not k.get("revoked", False)]

        if active_keys:
            # We can't retrieve the plaintext; create a new one
            pass

        resp = c.post(
            f"/api/v1/functions/{name}/keys",
            json={"label": "benchmark"},
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            return public_id, None
        api_key = resp.json().get("api_key")
        return public_id, api_key


# ── Main ──────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Code Executor Benchmark")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--public-id", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--concurrency", default="1,10,50", help="Comma-separated concurrency levels")
    parser.add_argument("--requests-per-level", type=int, default=30)
    parser.add_argument("--program", choices=["simple", "cpu"], default="simple")
    args = parser.parse_args()

    public_id = args.public_id
    api_key = args.api_key

    if not public_id or not api_key:
        print("[*] Auto-detecting function and API key...")
        det_pid, det_key = auto_detect(args.base_url)
        public_id = public_id or det_pid
        api_key = api_key or det_key
        if not public_id or not api_key:
            print("[!] Could not auto-detect.  Please provide --public-id and --api-key.")
            sys.exit(1)
        print(f"    public_id: {public_id}")
        print(f"    api_key:   {api_key[:12]}...")

    url = f"{args.base_url}/api/v1/f/{public_id}"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",
    }
    payload = SIMPLE_PROGRAM if args.program == "simple" else CPU_PROGRAM
    levels = [int(x.strip()) for x in args.concurrency.split(",")]

    print()
    print("=" * 60)
    print("  Code Executor Benchmark")
    print("=" * 60)
    print(f"  Endpoint:          {url}")
    print(f"  Program:           {args.program}")
    print(f"  Requests/level:    {args.requests_per_level}")
    print(f"  Concurrency:       {levels}")
    print("=" * 60)

    for level in levels:
        print(f"\n--- Concurrency: {level} ---")
        report = await run_level(url, headers, payload, level, args.requests_per_level)
        print(report.summary())

    print("\n" + "=" * 60)
    print("  Benchmark complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
