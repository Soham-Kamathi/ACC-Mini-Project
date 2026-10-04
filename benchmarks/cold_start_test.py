import time
import requests
import statistics
from common import BASE_URL, register_user, create_function, wait_for_status, require_k8s

def run_cold_vs_warm_benchmark(function_name="bench-calc", iterations=10):
    print("=" * 60)
    print(" EXPERIMENT 1: COLD START VS. WARM START LATENCY BENCHMARK ")
    print("=" * 60)

    # 1. Register test user & create function
    headers = register_user()
    print(f"[1] Creating function '{function_name}'...")
    create_function(headers, function_name)
    wait_for_status(headers, function_name, {"READY", "RUNNING"})

    # 2. Let the reaper scale it to zero so the first call is a genuine cold start
    print(f"[1b] Waiting for scale-to-zero (idle timeout + reaper interval)...")
    wait_for_status(headers, function_name, {"SCALED_TO_ZERO"}, timeout=300)

    # 3. Trigger Cold Start Invocation
    print("\n[2] Executing Cold Start Invocation...")
    cold_resp = requests.post(f"{BASE_URL}/invoke/{function_name}", headers=headers, json={"n": 25})
    cold_data = cold_resp.json()
    print(f"    Cold Start Response: {cold_data}")
    executed_on = [cold_data.get("executed_on")]
    assert cold_data.get("is_cold_start"), "first call was not a cold start"
    cold_total_ms = cold_data.get("total_duration_ms", 0.0)
    cold_provisioning_ms = cold_data.get("cold_start_duration_ms", 0.0)
    cold_exec_ms = cold_data.get("execution_duration_ms", 0.0)

    # 4. Trigger Warm Start Invocations
    print(f"\n[3] Executing {iterations} Warm Start Invocations...")
    warm_latencies = []
    for i in range(iterations):
        t0 = time.perf_counter()
        resp = requests.post(f"{BASE_URL}/invoke/{function_name}", headers=headers, json={"n": 25})
        executed_on.append(resp.json().get("executed_on"))
        warm_ms = (time.perf_counter() - t0) * 1000.0
        warm_latencies.append(warm_ms)
        time.sleep(0.05)

    require_k8s(executed_on)

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
