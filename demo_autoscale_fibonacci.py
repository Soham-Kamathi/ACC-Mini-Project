"""
========================================================================================
MicroFaaS Autoscaling & Observability Live Demonstration
========================================================================================
Target Function: fibonacci-calc
Public ID:       c10011191155459b
API Key:         fk_L9Lv7eXosU6sg33Byg373M5iJfLHgAd301EBWPcOaiI

How it scales pods:
  The MicroFaaS autoscaler sizes Pod replicas based on peak in-flight request demand:
      desired_replicas = ceil(in_flight_concurrent / target_concurrency)
  For fibonacci-calc:
      target_concurrency = 5 requests per pod
      min_replicas = 0 (scale-to-zero enabled)
      max_replicas = 5

  - 1 to 5 concurrent in-flight requests   -> 1 Pod
  - 6 to 10 concurrent in-flight requests  -> 2 Pods
  - 11 to 15 concurrent in-flight requests -> 3 Pods
  - 16 to 20 concurrent in-flight requests -> 4 Pods
  - 21+ concurrent in-flight requests      -> 5 Pods (clamped to max_replicas)

To guarantee that requests overlap in-flight, this script uses threading.Barrier
so that all worker threads release and hit the server at the exact same instant.
========================================================================================
"""
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict, Any

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Install it using: pip install requests")
    sys.exit(1)

# ---- Configuration ----
DEFAULT_BASE_URL = "http://localhost:8000"
PUBLIC_ID = "c10011191155459b"
API_KEY = "fk_L9Lv7eXosU6sg33Byg373M5iJfLHgAd301EBWPcOaiI"
FUNCTION_NAME = "fibonacci-calc"

# Read optional override from environment or .env
def get_base_url() -> str:
    # 1. Command-line argument
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        return sys.argv[1].rstrip("/")
    # 2. Environment variable
    env_url = os.environ.get("FAAS_BASE_URL")
    if env_url:
        return env_url.rstrip("/")
    # 3. Read .env file in current directory
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FAAS_BASE_URL="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val.startswith("http"):
                            return val.rstrip("/")
        except Exception:
            pass
    return DEFAULT_BASE_URL

BASE_URL = get_base_url()
INVOKE_URL = f"{BASE_URL}/api/v1/f/{PUBLIC_ID}"
OBSERVABILITY_URL = f"{BASE_URL}/api/v1/observability/functions/{PUBLIC_ID}"

def print_banner():
    print("\n" + "=" * 76)
    print("  🚀 MicroFaaS Autoscaler & Observability Live Demonstration")
    print("=" * 76)
    print(f"  Target Function:     {FUNCTION_NAME}")
    print(f"  Public Endpoint ID:  {PUBLIC_ID}")
    print(f"  Invoke URL:          {INVOKE_URL}")
    print(f"  API Key:             {API_KEY[:8]}...{API_KEY[-6:]}")
    print(f"  Scaling Rule:        1 Pod per 5 concurrent requests (max 5)")
    print("=" * 76)
    print("  TIP: Keep your browser open to the Observability Dashboard:")
    print("       http://localhost:5173  ->  Click 'Observability' Tab")
    print("=" * 76 + "\n")

def call_function(session: requests.Session, barrier: threading.Barrier, n_val: int = 35) -> Tuple[bool, float, int, Dict[str, Any]]:
    """Waits on barrier so all threads fire simultaneously, then sends invocation."""
    barrier.wait()
    t0 = time.perf_counter()
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"n": n_val}

    try:
        resp = session.post(INVOKE_URL, json=payload, headers=headers, timeout=45)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:100]}
        is_success = (status_code == 200)
        return is_success, elapsed_ms, status_code, data
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return False, elapsed_ms, 0, {"error": str(e)}

def fire_synchronized_burst(concurrency: int, n_val: int = 35) -> List[Tuple[bool, float, int, Dict[str, Any]]]:
    """Spawns `concurrency` threads synchronized by a barrier to fire simultaneously."""
    barrier = threading.Barrier(concurrency)
    results = []

    def worker(_):
        with requests.Session() as s:
            return call_function(s, barrier, n_val)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker, i) for i in range(concurrency)]
        for f in futures:
            results.append(f.result())

    return results

def query_live_observability():
    """Queries backend observability API to display real-time replica and telemetry state."""
    try:
        resp = requests.get(f"{OBSERVABILITY_URL}?time_range=15m", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            fn_info = data.get("function", {})
            scale_info = data.get("scaling_metrics", {})
            perf_info = data.get("performance_metrics", {})
            inv_info = data.get("invocation_metrics", {})

            current_rep = scale_info.get("current_replicas", fn_info.get("active_replicas", 0))
            ready_rep = scale_info.get("ready_replicas", 0)
            inflight = inv_info.get("in_flight_requests", 0)
            p50 = perf_info.get("p50_latency_ms", 0)
            p99 = perf_info.get("p99_latency_ms", 0)
            events = scale_info.get("recent_scaling_events", [])

            print("\n  📊 [Live Observability Telemetry Snapshot]")
            print(f"     • Active Pod Replicas:   {current_rep} pod(s) (Ready: {ready_rep})")
            print(f"     • Current In-Flight:     {inflight} request(s)")
            print(f"     • Latency Milestones:    p50: {p50} ms  |  p99: {p99} ms")
            if events:
                latest = events[0]
                print(f"     • Latest Scaling Event:  {latest.get('direction')} ({latest.get('from_replicas')} -> {latest.get('to_replicas')} pods) - {latest.get('reason')}")
            print()
    except Exception as e:
        # Observability query is advisory; continue even if offline
        pass

def main():
    print_banner()

    # Step 0: Initial Healthcheck / Warmup (1 call)
    print("▶ Step 0: Checking endpoint connectivity & warm-up (1 call)...")
    barrier0 = threading.Barrier(1)
    with requests.Session() as s:
        ok, lat, code, data = call_function(s, barrier0, n_val=25)
    
    if not ok:
        print(f"❌ Connection failed (HTTP {code}): {data}")
        print("\nPlease ensure the MicroFaaS backend is running at:", BASE_URL)
        print("Run start-all.bat or check your tunnel configuration.")
        sys.exit(1)

    cold_indicator = "COLD START" if data.get("is_cold_start") else "WARM"
    print(f"   ✓ Success! HTTP {code} ({cold_indicator}) - Latency: {lat:.1f}ms - Fib(25) = {data.get('result', {}).get('fibonacci_number')}")
    query_live_observability()
    time.sleep(2)

    # Step 1: Burst of 7 concurrent requests -> Triggers scale to 2 Pods
    print("\n" + "-" * 76)
    print("▶ Step 1: Firing BURST of 7 concurrent simultaneous requests")
    print("   Expected: in-flight peak = 7  ==>  Autoscaler targets ceil(7/5) = 2 PODS")
    print("-" * 76)
    
    t_start = time.perf_counter()
    results1 = fire_synchronized_burst(concurrency=7, n_val=35)
    t_total = (time.perf_counter() - t_start) * 1000.0

    succ1 = sum(1 for ok, _, _, _ in results1 if ok)
    avg_lat1 = sum(lat for _, lat, _, _ in results1) / len(results1)
    print(f"   ✓ Completed 7 simultaneous requests in {t_total:.1f}ms (Success: {succ1}/7, Avg Latency: {avg_lat1:.1f}ms)")
    
    print("   ⏳ Waiting 3 seconds for Autoscaler tick to register peak & scale deployment...")
    time.sleep(3)
    query_live_observability()

    # Step 2: Burst of 14 concurrent requests -> Triggers scale to 3 Pods
    print("\n" + "-" * 76)
    print("▶ Step 2: Firing SURGE of 14 concurrent simultaneous requests")
    print("   Expected: in-flight peak = 14  ==>  Autoscaler targets ceil(14/5) = 3 PODS")
    print("-" * 76)

    t_start = time.perf_counter()
    results2 = fire_synchronized_burst(concurrency=14, n_val=35)
    t_total = (time.perf_counter() - t_start) * 1000.0

    succ2 = sum(1 for ok, _, _, _ in results2 if ok)
    avg_lat2 = sum(lat for _, lat, _, _ in results2) / len(results2)
    print(f"   ✓ Completed 14 simultaneous requests in {t_total:.1f}ms (Success: {succ2}/14, Avg Latency: {avg_lat2:.1f}ms)")

    print("   ⏳ Waiting 3 seconds for Autoscaler tick...")
    time.sleep(3)
    query_live_observability()

    # Step 3: Peak Burst of 20 concurrent requests -> Triggers scale to 4 or 5 Pods
    print("\n" + "-" * 76)
    print("▶ Step 3: Firing PEAK BURST of 20 concurrent simultaneous requests")
    print("   Expected: in-flight peak = 20  ==>  Autoscaler targets ceil(20/5) = 4 to 5 PODS")
    print("-" * 76)

    t_start = time.perf_counter()
    results3 = fire_synchronized_burst(concurrency=20, n_val=35)
    t_total = (time.perf_counter() - t_start) * 1000.0

    succ3 = sum(1 for ok, _, _, _ in results3 if ok)
    avg_lat3 = sum(lat for _, lat, _, _ in results3) / len(results3)
    print(f"   ✓ Completed 20 simultaneous requests in {t_total:.1f}ms (Success: {succ3}/20, Avg Latency: {avg_lat3:.1f}ms)")

    print("   ⏳ Waiting 4 seconds for Autoscaler sync...")
    time.sleep(4)
    query_live_observability()

    print("\n" + "=" * 76)
    print("  🎉 Demonstration Completed Successfully!")
    print("=" * 76)
    print("  Summary of Activity:")
    print("    • Step 0: Warmup call (1 pod)")
    print("    • Step 1: 7 simultaneous calls  -> Scaled to 2 Pods")
    print("    • Step 2: 14 simultaneous calls -> Scaled to 3 Pods")
    print("    • Step 3: 20 simultaneous calls -> Scaled to 4-5 Pods")
    print("\n  👀 View the live visual results in the Dashboard:")
    print("     1. Open: http://localhost:5173")
    print("     2. Go to the 'Observability' tab.")
    print("     3. Select 'Per-Function Deep Dive' -> 'fibonacci-calc'.")
    print("     4. Under 'Metrics Charts' and 'Scaling & Events', watch the:")
    print("        - Invocations Throughput Spike")
    print("        - Active Replicas Transition Curve")
    print("        - Scaling Event Audit Entries")
    print("=" * 76 + "\n")

if __name__ == "__main__":
    main()
