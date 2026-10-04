"""
Experiment 3: replica scaling.

Part A (fixed replicas): the same CPU-bound function and the same load are run with exactly 1, 2, 5 and 10
replicas (min_replicas == max_replicas). Shows how throughput and tail latency change with replica count.

Part B (autoscaling): the function is allowed to scale between 1 and 10 replicas while a sustained load is
applied and then removed. Prints a timeline of desired/ready replicas, showing scale-up under load and the
damped scale-down afterwards.

Run the backend with ALLOW_LOCAL_SANDBOX=false (the default). The script aborts if any call did not run in a Pod.

    python benchmarks/scaling_test.py                 # both parts
    python benchmarks/scaling_test.py --part fixed --requests 600 --concurrency 60
"""
import argparse
import asyncio
import statistics
import time

import httpx
import requests

from common import BASE_URL, register_user, create_function, wait_for_status, require_k8s

# CPU-bound on purpose: a handler that returns instantly would measure the proxy path, not the Pods.
CPU_CODE = """def handler(event):
    total = 0
    for i in range(int(event.get("iters", 1500000))):
        total += i * i
    return {"total": total}
"""
FUNCTION = "scale-bench"
TIMEOUT_SECONDS = 60  # overloaded single Pods must queue, not hit the default 10s handler timeout


def set_scaling(headers, **fields):
    r = requests.put(f"{BASE_URL}/functions/{FUNCTION}", headers=headers, json=fields)
    r.raise_for_status()


def scaling_state(headers):
    return requests.get(f"{BASE_URL}/functions/{FUNCTION}/scaling", headers=headers).json()


def wait_for_ready_replicas(headers, n, timeout=240):
    deadline = time.time() + timeout
    state = {}
    while time.time() < deadline:
        state = scaling_state(headers)
        if state.get("ready_replicas") == n and state.get("desired_replicas") == n:
            return
        time.sleep(2)
    raise TimeoutError(f"Never reached {n} ready replicas (last state: {state})")


async def one_call(client, headers, sem, out):
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.post(f"{BASE_URL}/invoke/{FUNCTION}", headers=headers, json={})
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            ok = resp.status_code == 200 and body.get("status_code") == 200
            reason = None if ok else f"HTTP {resp.status_code} / fn {body.get('status_code')}: {str(body.get('error') or body.get('detail'))[:70]}"
            out.append({"ok": ok, "ms": (time.perf_counter() - t0) * 1000.0,
                        "executed_on": body.get("executed_on"), "reason": reason})
        except Exception as e:
            out.append({"ok": False, "ms": (time.perf_counter() - t0) * 1000.0, "executed_on": None,
                        "reason": f"client error: {type(e).__name__}"})


async def run_load(headers, total, concurrency):
    out, sem = [], asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency + 10)
    async with httpx.AsyncClient(timeout=60.0, limits=limits) as client:
        t0 = time.perf_counter()
        await asyncio.gather(*[one_call(client, headers, sem, out) for _ in range(total)])
        elapsed = time.perf_counter() - t0
    return out, elapsed


def summarize(results, elapsed):
    ok = [r for r in results if r["ok"]]
    reasons = {}
    for r in results:
        if not r["ok"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    require_k8s([r["executed_on"] for r in ok])
    lat = sorted(r["ms"] for r in ok)
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else 0.0
    return {
        "rps": len(ok) / elapsed if elapsed else 0.0,
        "ok": len(ok), "total": len(results),
        "mean": statistics.mean(lat) if lat else 0.0,
        "p50": p(0.50), "p95": p(0.95), "p99": p(0.99),
        "reasons": reasons,
    }


def part_fixed(headers, total, concurrency):
    print("\n" + "=" * 72)
    print(f" PART A: FIXED REPLICAS  ({total} requests, {concurrency} concurrent)")
    print("=" * 72)
    rows = []
    for n in (1, 2, 5, 10):
        print(f"\n---> {n} replica(s): scaling and waiting for readiness...")
        set_scaling(headers, min_replicas=n, max_replicas=n)
        wait_for_ready_replicas(headers, n)
        asyncio.run(run_load(headers, 30, 10))  # warm-up, not measured
        results, elapsed = asyncio.run(run_load(headers, total, concurrency))
        s = summarize(results, elapsed)
        rows.append((n, s))
        print(f"     throughput {s['rps']:.1f} req/s | ok {s['ok']}/{s['total']} | "
              f"p50 {s['p50']:.0f} ms | p95 {s['p95']:.0f} ms")
        for reason, count in s["reasons"].items():
            print(f"       {count} failed: {reason}")
    base = rows[0][1]["rps"] or 1.0
    print("\n Replicas | Throughput (req/s) | Speedup | Mean (ms) |  p50 (ms) |  p95 (ms) |  p99 (ms) | Success")
    print(" ---------+--------------------+---------+-----------+-----------+-----------+-----------+--------")
    for n, s in rows:
        print(f" {n:>8} | {s['rps']:>18.1f} | {s['rps'] / base:>6.2f}x | {s['mean']:>9.0f} | "
              f"{s['p50']:>9.0f} | {s['p95']:>9.0f} | {s['p99']:>9.0f} | {s['ok']}/{s['total']}")


async def sampler(headers, stop, timeline, t0):
    while not stop.is_set():
        state = await asyncio.to_thread(scaling_state, headers)
        timeline.append((time.time() - t0, state.get("desired_replicas"), state.get("ready_replicas"), state.get("in_flight_peak")))
        try:
            await asyncio.wait_for(stop.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


async def sustained_load(headers, concurrency, seconds):
    results, deadline = [], time.time() + seconds
    async with httpx.AsyncClient(timeout=60.0, limits=httpx.Limits(max_connections=concurrency + 10)) as client:
        async def worker():
            sem = asyncio.Semaphore(1)
            while time.time() < deadline:
                await one_call(client, headers, sem, results)
        await asyncio.gather(*[worker() for _ in range(concurrency)])
    return results


async def part_auto_async(headers, concurrency, seconds, cooldown):
    timeline, stop, t0 = [], asyncio.Event(), time.time()
    task = asyncio.create_task(sampler(headers, stop, timeline, t0))
    await asyncio.sleep(4)
    load_start = time.time() - t0
    results = await sustained_load(headers, concurrency, seconds)
    load_end = time.time() - t0
    await asyncio.sleep(cooldown)
    stop.set()
    await task
    return results, timeline, load_start, load_end


def part_auto(headers, concurrency, seconds, cooldown):
    print("\n" + "=" * 72)
    print(f" PART B: AUTOSCALING  (min 1, max 10, target 5 in flight per Pod, {concurrency} concurrent for {seconds}s)")
    print("=" * 72)
    set_scaling(headers, min_replicas=1, max_replicas=10, target_concurrency=5)
    wait_for_ready_replicas(headers, 1)
    results, timeline, load_start, load_end = asyncio.run(part_auto_async(headers, concurrency, seconds, cooldown))
    s = summarize(results, seconds)
    print(f"\n Load: {s['ok']}/{s['total']} ok, {s['rps']:.1f} req/s, p50 {s['p50']:.0f} ms, p95 {s['p95']:.0f} ms")
    for reason, count in s["reasons"].items():
        print(f" {count} failed: {reason}")
    print("\n  t (s) | demand (in flight) | desired | ready | phase")
    print("  ------+--------------------+---------+-------+----------------")
    for t, desired, ready, demand in timeline:
        phase = "baseline" if t < load_start else ("under load" if t <= load_end else "load removed")
        print(f"  {t:>5.0f} | {str(demand):>18} | {str(desired):>7} | {str(ready):>5} | {phase}")
    peak = max((d or 0) for _, d, _, _ in timeline)
    print(f"\n Peak desired replicas: {peak}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["fixed", "auto", "both"], default="both")
    ap.add_argument("--requests", type=int, default=200, help="requests per replica level (part A)")
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--load-seconds", type=int, default=40, help="sustained load duration (part B)")
    ap.add_argument("--cooldown-seconds", type=int, default=75, help="observe scale-down after the load stops (part B)")
    args = ap.parse_args()

    print("=" * 72)
    print(" EXPERIMENT 3: REPLICA SCALING")
    print("=" * 72)
    headers = register_user("scaleuser")
    create_function(headers, FUNCTION, CPU_CODE, timeout_seconds=TIMEOUT_SECONDS)
    wait_for_status(headers, FUNCTION, {"READY", "RUNNING"})
    if args.part in ("fixed", "both"):
        part_fixed(headers, args.requests, args.concurrency)
    if args.part in ("auto", "both"):
        part_auto(headers, args.concurrency, args.load_seconds, args.cooldown_seconds)


if __name__ == "__main__":
    main()
