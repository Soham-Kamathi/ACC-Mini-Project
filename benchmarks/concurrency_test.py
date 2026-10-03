import asyncio
import time
import httpx
import statistics

BASE_URL = "http://127.0.0.1:8000/api/v1"

async def send_request(client: httpx.AsyncClient, function_name: str, payload: dict):
    t0 = time.perf_counter()
    try:
        resp = await client.post(f"{BASE_URL}/invoke/{function_name}", json=payload)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {"success": resp.status_code == 200, "latency_ms": latency_ms, "status": resp.status_code}
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {"success": False, "latency_ms": latency_ms, "error": str(e)}

async def run_concurrency_tier(function_name: str, concurrency_level: int):
    print(f"\n---> Testing Concurrency Level: {concurrency_level} simultaneous requests...")
    payload = {"x": 42}

    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
        start_time = time.perf_counter()
        tasks = [send_request(client, function_name, payload) for _ in range(concurrency_level)]
        results = await asyncio.gather(*tasks)
        total_time_s = time.perf_counter() - start_time

    latencies = [r["latency_ms"] for r in results if r["success"]]
    success_count = sum(1 for r in results if r["success"])
    error_count = concurrency_level - success_count
    rps = concurrency_level / total_time_s if total_time_s > 0 else 0

    avg_lat = statistics.mean(latencies) if latencies else 0
    p95_lat = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0)

    print(f"     Total Duration:       {total_time_s:.2f} s")
    print(f"     Throughput (RPS):     {rps:.1f} req/sec")
    print(f"     Success / Fail:       {success_count} / {error_count} ({(success_count/concurrency_level)*100:.1f}%)")
    print(f"     Avg Latency:          {avg_lat:.2f} ms")
    print(f"     95th Percentile:      {p95_lat:.2f} ms")
    errors = [r.get("error") or f"status {r.get('status')}" for r in results if not r["success"]]
    if errors:
        print(f"     Sample Error:         {errors[0]}")

async def main():
    print("=" * 60)
    print(" EXPERIMENT 2: CONCURRENCY & THROUGHPUT LOAD TEST ")
    print("=" * 60)
    
    function_name = "bench-calc"
    for tier in [1, 10, 50, 100]:
        await run_concurrency_tier(function_name, tier)
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
