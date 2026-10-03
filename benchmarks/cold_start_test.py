import time
import requests
import json
import statistics

BASE_URL = "http://127.0.0.1:8000/api/v1"

def run_cold_vs_warm_benchmark(function_name="bench-calc", iterations=10):
    print("=" * 60)
    print(" EXPERIMENT 1: COLD START VS. WARM START LATENCY BENCHMARK ")
    print("=" * 60)

    # 1. Register test user & login
    username = f"benchuser_{int(time.time())}"
    reg_resp = requests.post(f"{BASE_URL}/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "password": "Password123!"
    })
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create function
    code = """def handler(event):
    n = event.get("n", 30)
    # CPU calculation: Fibonacci
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {"fibonacci": a, "n": n}
"""
    print(f"[1] Creating function '{function_name}'...")
    create_resp = requests.post(f"{BASE_URL}/functions/", headers=headers, json={
        "name": function_name,
        "runtime": "python311",
        "code": code,
        "description": "Fibonacci calculation for cold/warm latency benchmarking"
    })
    print(f"    Status: {create_resp.status_code}")

    # Wait for ready
    time.sleep(2)

    # 3. Trigger Cold Start Invocation
    print("\n[2] Executing Cold Start Invocation...")
    cold_resp = requests.post(f"{BASE_URL}/invoke/{function_name}", json={"n": 25})
    cold_data = cold_resp.json()
    print(f"    Cold Start Response: {cold_data}")
    cold_total_ms = cold_data.get("total_duration_ms", 0.0)
    cold_provisioning_ms = cold_data.get("cold_start_duration_ms", 0.0)
    cold_exec_ms = cold_data.get("execution_duration_ms", 0.0)

    # 4. Trigger Warm Start Invocations
    print(f"\n[3] Executing {iterations} Warm Start Invocations...")
    warm_latencies = []
    for i in range(iterations):
        t0 = time.perf_counter()
        resp = requests.post(f"{BASE_URL}/invoke/{function_name}", json={"n": 25})
        warm_ms = (time.perf_counter() - t0) * 1000.0
        warm_latencies.append(warm_ms)
        time.sleep(0.05)

    # 5. Summarize Results
    avg_warm = statistics.mean(warm_latencies)
    median_warm = statistics.median(warm_latencies)
    min_warm = min(warm_latencies)
    max_warm = max(warm_latencies)
    speedup = cold_total_ms / avg_warm if avg_warm > 0 else 0

    print("\n" + "=" * 60)
    print(" BENCHMARK RESULTS SUMMARY ")
    print("=" * 60)
    print(f" Cold Start Total Latency:       {cold_total_ms:.2f} ms")
    print(f"   |-- Container Provisioning:    {cold_provisioning_ms:.2f} ms")
    print(f"   \\-- Function Execution Time:   {cold_exec_ms:.2f} ms")
    print("-" * 60)
    print(f" Warm Start Mean Latency:        {avg_warm:.2f} ms")
    print(f" Warm Start Median (p50):        {median_warm:.2f} ms")
    print(f" Warm Start Min / Max:           {min_warm:.2f} ms / {max_warm:.2f} ms")
    print(f" Warm vs. Cold Speedup:          {speedup:.1f}x faster when warm")
    print("=" * 60)

if __name__ == "__main__":
    run_cold_vs_warm_benchmark()
