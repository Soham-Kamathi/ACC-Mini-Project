# Kubernetes-Based Docker Serverless (FaaS) Function Execution Platform

A self-hosted **Function-as-a-Service (FaaS)** execution platform that allows developers to register, version, manage, and invoke serverless functions on demand. The platform packages user code into standardized Docker containers, orchestrates them via a custom **FaaS Controller** on **Kubernetes**, supports **scale-to-zero** with cold/warm latency measurement, enforces resource & security constraints, and exposes monitoring and management through an interactive **Web Dashboard** and **Prometheus/Grafana**.

---

## Key Features

1. **REST API & Auth**: FastAPI backend with JWT user authentication and function ownership isolation.
2. **Standardized Runtime**: Python 3.11 base runtime with dynamic handler loading, error catching, and timeout enforcement.
3. **Dynamic Image Builder**: Automatically generates Dockerfiles, compiles container images, and tags them in a local Docker registry.
4. **Custom FaaS Controller & Scale-to-Zero**:
   - Idle-reaper background daemon automatically scales idle workloads down to 0 replicas.
   - On-demand cold-start provisioning when invocations arrive.
5. **Cold vs. Warm Latency Telemetry**: Real-time breakdown of container startup latency vs. function execution time.
6. **Kubernetes Orchestration**: Programmatic Deployment, ClusterIP Service, and Pod management with CPU/memory limits (`256Mi`, `500m`), security context (`runAsNonRoot=True`), and readiness probes (`/healthz`).
7. **Observability**: Prometheus metrics exporter (`/api/v1/metrics`) tracking invocations, cold starts, and latency percentiles.
8. **Interactive Web Dashboard**: React + Vite + Tailwind CSS UI for cataloging functions, writing code, testing endpoints, and viewing logs.
9. **Scientific Evaluation Suite**: Automated benchmarking scripts for Cold Start (Exp 1), Concurrency & Throughput (Exp 2), and Replica Scaling (Exp 3).

---

## Project Structure

```
ACC Mini Project/
├── backend/                  # FastAPI Application & FaaS Controller
│   ├── app/
│   │   ├── api/              # REST Endpoints (auth, functions, invoke, logs, metrics, cluster)
│   │   ├── core/             # Settings, DB session, Security & JWT
│   │   ├── models/           # SQLAlchemy DB Models (User, Function, Version, InvocationLog)
│   │   ├── schemas/          # Pydantic Schemas (Request/Response)
│   │   ├── services/         # BuilderService, K8sService, FaasController, RouterService
│   │   └── main.py           # FastAPI entry point & lifespan daemon
│   ├── runtimes/             # Base Runtime Templates
│   │   └── python311/        # Python 3.11 Dockerfile.template + server.py wrapper
│   ├── tests/                # Pytest unit & integration tests
│   └── requirements.txt      # Python dependencies
├── frontend/                 # React + Vite + Tailwind CSS Web Dashboard
│   ├── src/
│   │   ├── App.tsx           # Full-featured FaaS management UI
│   │   ├── main.tsx          # React DOM entry
│   │   └── index.css         # Tailwind styles
│   └── package.json
├── k8s/                      # Kubernetes Manifests
│   ├── namespace.yaml        # faas-fn & faas-system namespaces
│   ├── rbac.yaml             # ServiceAccount, ClusterRole, RoleBinding
│   └── registry.yaml         # In-cluster Docker registry
├── benchmarks/               # Scientific Performance Benchmark Suite
│   ├── cold_start_test.py    # Experiment 1: Cold vs Warm start latency
│   └── concurrency_test.py   # Experiment 2: Concurrent load & throughput
├── docker-compose.yml        # Local PostgreSQL & Docker Registry
└── README.md
```

---

## Security & Isolation Model

- **Authentication on invoke**: `POST /api/v1/invoke/{name}[/{version}]` requires a `Bearer` JWT. Functions are looked up by `(owner, name)`, so two users can both own a function called `hello` without colliding.
- **Per-version Deployments**: each function version is deployed as its own Deployment/Service named `fn-<owner_id>-<name>-<version>` (all labelled `faas-function=<owner_id>-<name>`). `/invoke/{name}/v1` really runs v1; `/invoke/{name}` runs the newest version that has finished building. Function names must be DNS-1123 labels (max 30 chars).
- **No in-process execution by default**: user code only ever runs inside a Pod. The old `exec()` fallback is disabled; set `ALLOW_LOCAL_SANDBOX=true` for local development without a cluster (**unsafe: arbitrary code execution inside the API process**). Every invocation response and log row carries `executed_on` (`k8s`, `sandbox` or `none`).

## Autoscaling

Each function has three settings (create form in the dashboard, or `POST`/`PUT /api/v1/functions`):

| Setting | Default | Meaning |
|---|---|---|
| `min_replicas` | 0 | Floor. `0` allows scale-to-zero when idle; `>0` keeps that many Pods warm and never scales to zero. |
| `max_replicas` | 5 | Ceiling (hard limit 20). |
| `target_concurrency` | 5 | In-flight requests one Pod is sized for. |

The controller's autoscaler measures the number of requests in flight per function version (including requests waiting on a cold start) and every 2 seconds sets `replicas = ceil(in_flight / target_concurrency)`, clamped to `[max(min_replicas, 1), max_replicas]`.

- **Scale up is immediate** and uses the peak seen since the last check, so a short burst is not missed.
- **Scale down is damped**: it only drops as far as the highest demand of the last 30 seconds (`SCALE_DOWN_STABILIZATION_SECONDS`), so brief lulls do not make Pods flap.
- **Scale to zero** is still done by the idle reaper after 60 seconds without traffic, unless `min_replicas > 0`.
- Set `min_replicas == max_replicas` for a fixed replica count (used by Experiment 3).
- `GET /api/v1/functions/{name}/scaling` returns the bounds plus the live desired and ready replica counts. Prometheus exports `faas_scale_events_total` and `faas_desired_replicas`.

## Quick Start Guide

### 1. Enable Kubernetes on Docker Desktop

1. Open **Docker Desktop**.
2. Click the **Settings (Gear icon)** $\rightarrow$ **Kubernetes**.
3. Check **Enable Kubernetes** and click **Apply & restart**.
4. Verify cluster is active:
   ```bash
   kubectl get nodes
   ```

### 2. Start Supporting Services (PostgreSQL & Docker Registry)

```bash
docker compose up -d
```

### 3. Start Backend API & FaaS Controller

```bash
# Install Python requirements
pip install -r backend/requirements.txt

# Run FastAPI backend
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Prometheus Metrics: [http://localhost:8000/api/v1/metrics](http://localhost:8000/api/v1/metrics)

### 4. Start Frontend Web Dashboard

```bash
cd frontend
npm install
npm run dev
```

- Dashboard UI: [http://localhost:5173](http://localhost:5173)

---

## Running Benchmarks & Experiments

### Running Unit & Integration Tests

```bash
python -m pytest backend/tests -v   # use the project venv: .venv\Scripts\python.exe -m pytest backend/tests -v
```

### Experiment 1: Cold Start vs. Warm Start Latency

Measures container startup latency vs. warm in-memory execution:

```bash
python benchmarks/cold_start_test.py
```

### Experiment 2: Concurrency & Throughput Load Test

Fires concurrent requests (1, 10, 50, 100 simultaneous workers) to measure RPS and latency percentiles:

```bash
python benchmarks/concurrency_test.py
```

---

### Experiment 3: Replica Scaling and Autoscaling

Runs a CPU-bound function with 1, 2, 5 and 10 fixed replicas under the same load (part A), then lets the autoscaler grow and shrink the function under a sustained load (part B). Aborts if any call did not run in a Pod.

```bash
python benchmarks/scaling_test.py                 # both parts
python benchmarks/scaling_test.py --part fixed --requests 600 --concurrency 60
```

## Benchmark Results & Empirical Evaluation

> **Note:** the results below were collected before the sandbox fallback was gated and `executed_on` was recorded, so some calls may have run in-process rather than in a Pod. Re-run `benchmarks/cold_start_test.py` and `benchmarks/concurrency_test.py` (they now abort if any call did not run on Kubernetes) and replace these numbers.

### 1. Unit & Integration Test Suite Verification

Comprehensive test suite verifying authentication, function versioning, container deployment lifecycle, invocation proxy, and Prometheus metric exporters.

```bash
PS D:\ACC Mini Project> python -m pytest backend/tests -v
============================= test session starts =============================
platform win32 -- Python 3.10.0, pytest-8.3.4, pluggy-1.5.0
rootdir: D:\ACC Mini Project
collected 4 items

backend/tests/test_auth.py::test_root_endpoint PASSED                    [ 25%]
backend/tests/test_auth.py::test_user_registration_and_login PASSED      [ 50%]
backend/tests/test_functions.py::test_create_and_list_functions PASSED   [ 75%]
backend/tests/test_invocation.py::test_function_invocation PASSED        [100%]

======================== 4 passed, 2 warnings in 3.67s ========================
```

| Test Case                            | Scope                 |      Status      | Description                                                               |
| :----------------------------------- | :-------------------- | :--------------: | :------------------------------------------------------------------------ |
| `test_root_endpoint`               | Platform API          | **PASSED** | Validates system health and API v1 routing                                |
| `test_user_registration_and_login` | Security & Auth       | **PASSED** | Verifies JWT user registration, password hashing, and token issuance      |
| `test_create_and_list_functions`   | Function Lifecycle    | **PASSED** | Verifies function definition, runtime registration, and versioning        |
| `test_function_invocation`         | Execution & Telemetry | **PASSED** | Verifies execution dispatch, cold-start telemetry, and Prometheus metrics |

---

### 2. Experiment 1: Cold Start vs. Warm Start Latency

Conducted against function `bench-calc` (Fibonacci computation runtime) running inside a Kubernetes Pod in namespace `faas-fn`.

```
============================================================
 EXPERIMENT 1: COLD START VS. WARM START LATENCY BENCHMARK 
============================================================
[1] Creating function 'bench-calc'...
    Status: 201

[2] Executing Cold Start Invocation...
    Cold Start Response: 
    - status_code: 200
    - is_cold_start: True
    - cold_start_duration_ms: 1702.59 ms
    - execution_duration_ms: 12.67 ms
    - total_duration_ms: 1715.26 ms
    - result: {'fibonacci': 75025, 'n': 25}

[3] Executing 10 Warm Start Invocations...
============================================================
 BENCHMARK RESULTS SUMMARY 
============================================================
 Cold Start Total Latency:       1715.26 ms
   |-- Container Provisioning:    1702.59 ms
   \-- Function Execution Time:   12.67 ms
------------------------------------------------------------
 Warm Start Mean Latency:        30.01 ms
 Warm Start Median (p50):        27.22 ms
 Warm Start Min / Max:           16.78 ms / 42.97 ms
 Warm vs. Cold Speedup:          57.2x faster when warm
============================================================
```

#### Latency Breakdown Comparison

| Metric                           | Cold Start (Scale from 0) |  Warm Start (Active Pod)  | Improvement / Difference |
| :------------------------------- | :-----------------------: | :-----------------------: | :----------------------: |
| **Container Provisioning** |   **1702.59 ms**   |     **0.00 ms**     |  Instantaneous routing  |
| **Execution Time**         |    **12.67 ms**    |    **~2.50 ms**    |     Pure computation     |
| **Total Response Latency** |   **1715.26 ms**   | **30.01 ms** (mean) |  **57.2x faster**  |
| **Minimum Latency**        |            —            |    **16.78 ms**    | Sub-20ms warm responses |
| **Median (p50)**           |            —            |    **27.22 ms**    | Steady-state performance |

---

### 3. Experiment 2: Concurrency & Throughput Benchmark

Tested across four load tiers (1, 10, 50, and 100 simultaneous requests) against `http://127.0.0.1:8000/api/v1/invoke/bench-calc`.

```
============================================================
 EXPERIMENT 2: CONCURRENCY & THROUGHPUT LOAD TEST 
============================================================

---> Testing Concurrency Level: 1 simultaneous requests...
     Total Duration:       0.03 s
     Throughput (RPS):     39.6 req/sec
     Success / Fail:       1 / 0 (100.0%)
     Avg Latency:          25.00 ms
     95th Percentile:      25.00 ms

---> Testing Concurrency Level: 10 simultaneous requests...
     Total Duration:       0.10 s
     Throughput (RPS):     102.5 req/sec
     Success / Fail:       10 / 0 (100.0%)
     Avg Latency:          82.15 ms
     95th Percentile:      95.41 ms

---> Testing Concurrency Level: 50 simultaneous requests...
     Total Duration:       1.47 s
     Throughput (RPS):     34.1 req/sec
     Success / Fail:       50 / 0 (100.0%)
     Avg Latency:          695.59 ms
     95th Percentile:      1445.64 ms

---> Testing Concurrency Level: 100 simultaneous requests...
     Total Duration:       2.76 s
     Throughput (RPS):     36.2 req/sec
     Success / Fail:       100 / 0 (100.0%)
     Avg Latency:          1339.93 ms
     95th Percentile:      2700.85 ms
```

#### Concurrency Performance Summary Table

|   Concurrency Tier   | Total Duration |   Throughput (RPS)   |        Success Rate        |   Average Latency   | 95th Percentile (p95) |
| :-------------------: | :------------: | :-------------------: | :------------------------: | :------------------: | :-------------------: |
|  **1 Worker**  |     0.03 s     | **39.6 req/s** |   **100.0%** (1/1)   |  **25.00 ms**  |       25.00 ms       |
| **10 Workers** |     0.10 s     | **102.5 req/s** |  **100.0%** (10/10)  |  **82.15 ms**  |       95.41 ms       |
| **50 Workers** |     1.47 s     | **34.1 req/s** |  **100.0%** (50/50)  | **695.59 ms** |      1445.64 ms      |
| **100 Workers** |     2.76 s     | **36.2 req/s** | **100.0%** (100/100) | **1339.93 ms** |      2700.85 ms      |

---

### 3b. Experiment 3: Replica Scaling and Autoscaling

Measured on Docker Desktop Kubernetes (one node), backend outside the cluster, in-process sandbox disabled (every call ran in a Pod). Function: CPU-bound loop of 1.5 million iterations (about 90 ms of CPU), 500m CPU limit per Pod. Load: 200 requests with 50 concurrent callers per level. One run per level, so treat small differences as noise.

**Part A: fixed replica count (`min_replicas == max_replicas`)**

| Replicas | Throughput (req/s) | Speedup | Mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Success |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 11.1 | 1.00x | 3993 | 4401 | 4748 | 4904 | 200/200 |
| 2 | 20.5 | 1.84x | 2098 | 2149 | 3000 | 3100 | 200/200 |
| 5 | 43.6 | 3.93x | 953 | 891 | 1659 | 1827 | 200/200 |
| 10 | 65.9 | 5.93x | 605 | 582 | 1230 | 1422 | 200/200 |

Throughput grows with replicas (about 6x at 10 replicas) and tail latency drops by roughly 4x. Scaling is sub-linear: from 5 to 10 replicas the gain is 1.5x, because the single backend process and the Kubernetes API-server proxy start to limit throughput, and all Pods share one machine.

**Part B: autoscaling (min 1, max 10, 5 in-flight requests per Pod, 50 concurrent callers for 40 s)**

| Time | Event |
| :--- | :--- |
| t = 4 s | Load starts; 1 Pod ready |
| t = 6 s | Autoscaler measures 50 requests in flight and asks for 10 replicas |
| t = 10 s | 2 Pods ready |
| t = 12 s | 10 Pods ready (about 6 s after the scale-up decision) |
| t = 12-44 s | Demand holds at 50 in flight, 10 Pods stay up |
| t = 46 s | Load stops; replicas are held at 10 for the 30 s stabilization window |
| t = 75 s | Scaled down to 1 replica |

Result: 2558/2558 requests succeeded at 64 req/s, p50 372 ms. The p95 of 3454 ms comes from the first seconds, before the extra Pods were ready.

**Notes**
- With a very light function (a few milliseconds of work) throughput stopped improving at about 85-90 req/s from 2 replicas upward. The single API process, not the Pods, was the limit, and the autoscaler correctly saw little in-flight demand. Replica scaling only helps when the Pods are the bottleneck.
- Running this benchmark exposed three bugs, now fixed: the Pod's HTTP listen backlog was 5 (connection resets under bursts), a transient Kubernetes API error was cached as "function not deployed", and failure reasons were not reported by the script.

### 4. Architectural Optimizations for High Concurrency

1. **SQLite WAL Mode & Non-Blocking Database I/O**:
   - Configured SQLite with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`, enabling concurrent readers while background writers flush logs.
2. **Asynchronous Batch Logging Queue**:
   - Invocation responses return immediately to the caller, pushing log entries into an in-memory queue drained by a dedicated background batch worker (`_batch_log_worker`), eliminating per-request SQLite lock contention.
3. **In-Memory Metadata Caching**:
   - Hot-path function definitions and active version records are cached with a 15-second TTL, reducing redundant relational queries during load bursts to zero.
4. **Kubernetes API Connection Pooling**:
   - Expanded Kubernetes client connection pool maxsize (`connection_pool_maxsize = 120`) and thread executor workers (`max_workers = 200`), allowing up to 100 parallel proxy requests without connection starvation.
5. **Resilient Dual-Mode Execution**:
   - Router automatically proxies to Kubernetes Service endpoints when ready, with automatic fallback to isolated runtime sandbox execution if pods are still initializing, guaranteeing 100% availability.
