# Project Tasks & Progress Tracking

**Project Title:** Kubernetes-Based Docker Serverless (FaaS) Function Execution Platform  
**Directory:** `ACC-Mini-Project/`  
**Current Status:** ~78% Complete (Core platform, controller, scale-to-zero, dashboard, and 2 benchmarks operational; observability visualizer, scaling benchmark, and multi-runtime pending)

---

## 1. Overview & Progress Summary

| Layer / Component | Status | Estimated Completion | Key Accomplishments |
| :--- | :---: | :---: | :--- |
| **Backend REST API & Auth** | Done | 95% | FastAPI, JWT auth, bcrypt, ownership checks, SQLite WAL mode, async batch logging |
| **Function Lifecycle & Versions** | Done | 90% | v1/v2/v3 versioning, immutable code records, latest/versioned routing |
| **Custom FaaS Controller** | Done | 90% | Background reaper loop, 60s idle timeout detection, scale-to-zero |
| **Cold/Warm Telemetry** | Done | 95% | Sub-millisecond timing breakdown (provisioning vs execution), audit logging |
| **Dynamic Docker Builder** | Done | 85% | Automated Dockerfile assembly, temp context build, container tagging |
| **Kubernetes Orchestration** | Done | 85% | Deployments, ClusterIP Services, non-root security context, readiness probes |
| **Frontend Web Dashboard** | Done | 80% | React 18 + Tailwind, KPI stats, code studio, live invoker, audit logs |
| **Scientific Benchmarks** | Partial | 65% | Cold vs Warm test (Exp 1), Concurrency load test (Exp 2) working |
| **Prometheus & Grafana Stack** | Partial | 40% | Backend Prometheus exporter ready; Grafana & scrape config missing |
| **Multi-Language Runtimes** | Partial | 50% | Python 3.11 runtime fully implemented; Node.js runtime not yet added |

---

## 2. Completed Components & Features (`[x]`)

### 2.1 Backend API & Security Layer
- [x] **FastAPI Framework**: Modular REST API architecture using APIRouter under `/api/v1`.
- [x] **JWT Authentication**: User registration (`/auth/register`), login (`/auth/login`), password hashing with `passlib[bcrypt]`, and bearer token authentication (`/auth/me`).
- [x] **Tenant Isolation**: Functions and invocation logs are strictly isolated by `user_id` ownership.
- [x] **Database & ORM**: SQLAlchemy models for `User`, `Function`, `FunctionVersion`, and `InvocationLog`.
- [x] **High-Concurrency DB Optimizations**:
  - [x] SQLite configured with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`.
  - [x] Asynchronous background batch logging worker (`_batch_log_worker`) draining an in-memory queue to eliminate SQLite write-lock contention.
  - [x] 15-second TTL in-memory metadata caching for hot-path function lookups (`_fn_cache` and `_version_cache`).
- [x] **System Health & Cluster Endpoints**: `/cluster/status` reporting live health of Kubernetes, Docker daemon, and FaaS Controller reaper.

### 2.2 Function Management & Lifecycle
- [x] **Function CRUD Endpoints**:
  - [x] `POST /api/v1/functions/`: Registers function and triggers background container build & deployment.
  - [x] `GET /api/v1/functions/`: Lists functions owned by the authenticated tenant.
  - [x] `GET /api/v1/functions/{name}`: Retrieves full details including version history.
  - [x] `PUT /api/v1/functions/{name}`: Updates code and resource limits, automatically creating incremental versions (`v2`, `v3`).
  - [x] `DELETE /api/v1/functions/{name}`: Deletes DB records and cleans up Kubernetes Deployments and Services.
- [x] **Function State Machine**: Supports `CREATING`, `BUILDING`, `READY`, `RUNNING`, `IDLE`, `SCALED_TO_ZERO`, and `ERROR`.

### 2.3 FaaS Controller & Scale-to-Zero Engine
- [x] **Scale-to-Zero Daemon**: Background `FaasController` running an asynchronous periodic reaper loop (`_reaper_loop`) every 10 seconds.
- [x] **Inactivity Reaper**: Automatically identifies idle functions (`last_invoked_at > 60s`) and scales their Kubernetes Deployment replicas down to `0`.
- [x] **On-Demand Cold Start Activation**:
  - [x] Router detects `replicas == 0` or `status == "SCALED_TO_ZERO"`.
  - [x] Triggers `scale_deployment(name, 1)`.
  - [x] Polls Pod readiness probe (`/healthz`) until the container is ready.
  - [x] Captures container provisioning time in milliseconds (`cold_start_duration_ms`).
- [x] **Warm Start Routing**: Instant proxying to active Pod / Service when `replicas >= 1`.

### 2.4 Container Runtime & Image Builder
- [x] **Standardized Python 3.11 Runtime**:
  - [x] Base runtime container built on `python:3.11-slim`.
  - [x] In-container HTTP server (`server.py`) with dynamic handler loading (`handler(event)`).
  - [x] Dedicated `/healthz` probe endpoint on port 8080.
  - [x] Timeout enforcement using `concurrent.futures.ThreadPoolExecutor`.
  - [x] Structured JSON exception formatting and status code handling.
- [x] **Dynamic Container Image Builder**:
  - [x] Automated compilation via Docker Python SDK in `BuilderService`.
  - [x] Isolated temporary directory build context assembling user code, dependencies, and runtime wrapper.
  - [x] Automated image naming and tagging (`localhost:5000/{username}/{func_name}:{version}`).

### 2.5 Kubernetes Orchestration & Security Hardening
- [x] **Programmatic Resource Provisioning**: Automated creation of Kubernetes `Deployment` and `ClusterIP Service` inside namespace `faas-fn`.
- [x] **Container Security Context**:
  - [x] Enforces non-root execution (`runAsNonRoot=True`, `runAsUser=10001`).
  - [x] Drops all Linux capabilities (`capabilities: drop: ["ALL"]`).
  - [x] Disallows privilege escalation (`allowPrivilegeEscalation=False`).
- [x] **Resource Governance**:
  - [x] Default CPU limits (`500m`) and memory limits (`256Mi`).
  - [x] Default CPU requests (`100m`) and memory requests (`64Mi`).
- [x] **Readiness Probes**: Configured HTTP probe hitting port 8080 (`/healthz`).
- [x] **Dual-Mode Execution Fallback**: Automatic failover to local execution sandbox if Kubernetes is offline or Pod endpoints are still synchronizing.

### 2.6 Observability & Telemetry
- [x] **Prometheus Metrics Exporter**: Exposes `/api/v1/metrics` with standard metrics:
  - [x] `faas_invocations_total{function_name, status}` (Counter).
  - [x] `faas_cold_starts_total{function_name}` (Counter).
  - [x] `faas_invocation_duration_seconds{function_name, type="cold"|"warm"}` (Histogram).
  - [x] `faas_active_replicas{function_name}` (Gauge).
- [x] **Dashboard KPI Aggregation**: `/api/v1/stats` providing total functions, active replicas, cold-start counts, and latency averages.
- [x] **Invocation Audit Logging**: Granular logging of request ID, cold start boolean, latency breakdown, input/output payload, and error messages.

### 2.7 Frontend Web Dashboard
- [x] **Modern Single-Page Interface**: Built with React 18, Vite, Lucide icons, and Tailwind CSS.
- [x] **Developer Auth Flow**: Login and registration modal saving JWT into `localStorage`.
- [x] **Function Catalog View**: Cards displaying status badges, replica count, resource limits, and quick-delete / invoke triggers.
- [x] **Function Studio View**: In-browser code editor with starter templates (Hello World, Fibonacci, JSON Transformer), resource sliders, and deploy button.
- [x] **Interactive Invocation Console**: JSON payload editor, execute trigger, and a visual 3-way latency bar (Cold Start ms vs Execution ms vs Total ms).
- [x] **Invocation Logs View**: Execution history table with cold/warm indicators, timestamps, and request IDs.
- [x] **Cluster Health Tab**: Live indicator chips for Kubernetes, Docker, and the scale-to-zero reaper.

### 2.8 Scientific Benchmarking Suite
- [x] **Experiment 1 (Cold Start vs. Warm Start)**: `benchmarks/cold_start_test.py` measuring provisioning latency vs 10 warm executions and calculating speedup ratios.
- [x] **Experiment 2 (Concurrency & Throughput)**: `benchmarks/concurrency_test.py` utilizing `asyncio` and `httpx` to benchmark 1, 10, 50, and 100 concurrent workers.

---

## 3. Remaining Components & Unfinished Parts (`[ ]`)

### 3.1 Prometheus & Grafana Monitoring Stack
- [ ] **Grafana Container in Docker Compose**: `docker-compose.yml` currently only provisions PostgreSQL and Docker Registry; Prometheus and Grafana services are absent.
- [ ] **Prometheus Scrape Configuration**: Missing `prometheus.yml` to automatically scrape the backend's `/api/v1/metrics` endpoint.
- [ ] **Pre-configured Grafana Dashboard JSON**: Exported dashboard displaying cold-start ratios, RPS throughput, and latency percentiles (p50, p95, p99).

### 3.2 Experiment 3 / 4 (Replica Scaling Benchmark)
- [ ] **Replica Scaling Benchmark Script**: The README and architecture guide reference "Replica Scaling (Exp 3)" and measuring performance across 1, 2, 5, and 10 replicas, but there is no dedicated script (e.g., `benchmarks/scaling_test.py`) in the codebase.
- [ ] **Empirical Benchmark Documentation**: Add benchmark output logs and evaluation tables for the scaling experiment to `README.md`.

### 3.3 Multi-Language Runtime Support
- [ ] **Node.js Runtime Template**: Add `backend/runtimes/nodejs18/` or `nodejs20/` with `server.js` and `Dockerfile.template` to demonstrate multi-language support (a core feature mentioned in the FaaS design discussion).
- [ ] **Runtime Selector in Frontend**: Add Node.js template and runtime toggle in the Function Studio UI.

### 3.4 Invocation Stdout / Stderr Log Streaming
- [ ] **Container Log Capture**: Capture user `print()` / stdout / stderr output during execution and return it in `InvokeResponse` and `InvocationLog`.
- [ ] **Log Streamer / Terminal in UI**: Allow developers to inspect console output generated during function execution directly in the dashboard.

### 3.5 Function Version Management & UI Editing
- [ ] **Frontend Edit Function Flow**: Provide an "Edit / Update" button in the Function Catalog card that loads existing source code into the Studio and triggers `PUT /api/v1/functions/{name}`.
- [ ] **Version Selector for Invocation**: Allow testing specific versions (e.g. `v1` vs `v2`) directly from the Invocation Console (currently defaults to latest).

### 3.6 Function Environment Variables & Secrets
- [ ] **Configurable Environment Variables**: Add optional `environment_variables: Dict[str, str]` to `FunctionCreate` and inject them into the Kubernetes Pod container `env`.

### 3.7 Manual Scaling Controls
- [ ] **Manual Scale Button in UI**: Allow users or admins to trigger manual scale-to-zero or pre-warm up (`scale to 1`) directly from the Function Catalog card.

---

## 4. Minor Modifications & Recommended Fixes

### 4.1 Resilient Dependency Imports (Fallback Mode)
- **Issue**: `from kubernetes import client, config` in `k8s_client.py` and `import docker` in `builder.py` are imported at the top level without try-except guards.
- **Problem**: If `kubernetes` or `docker` packages are not installed in the local Python environment, the backend crashes immediately during import, preventing fallback sandbox mode from running.
- **Modification**: Wrap `import docker` and `from kubernetes import ...` in `try-except ImportError` blocks with graceful fallback flags.

### 4.2 Localhost Docker Registry Push Logic
- **Issue**: In `backend/app/services/builder.py`, line 65:
  ```python
  if settings.DOCKER_REGISTRY and not settings.DOCKER_REGISTRY.startswith("localhost"):
      self.client.images.push(image_name)
  ```
- **Problem**: This explicitly skips pushing to `localhost:5000` (the default local registry)! If Kubernetes runs on Minikube, KinD, or another node, Kubernetes cannot pull the image unless it is pushed to the registry.
- **Modification**: Remove the `not startswith("localhost")` check or allow push when `localhost:5000` is active.

### 4.3 Pytest Configuration File (`pytest.ini`)
- **Issue**: Running `pytest` can produce warnings or errors regarding `asyncio_mode` and unhandled warning filters.
- **Modification**: Add a clean `pytest.ini` in the project root configuring `asyncio_mode = auto` and test discovery paths.

### 4.4 Documentation Link Portability
- **Issue**: `PROJECT_ARCHITECTURE_GUIDE.md` contains file links hardcoded with `file:///d:/ACC%20Mini%20Project/...`.
- **Modification**: Update links to relative markdown links or workspace-relative URIs so they work across different machines and drives.

### 4.5 Vite Environment Variable for API Base
- **Issue**: In `frontend/src/App.tsx`, `const API_BASE = '/api/v1'` is hardcoded.
- **Modification**: Use `import.meta.env.VITE_API_URL || '/api/v1'` to enable seamless deployment when backend and frontend are hosted on different ports or domains.

---

## 5. Priority Action Plan

1. **Step 1 (Fix Robustness)**: Update `backend/app/services/k8s_client.py` and `builder.py` to handle optional imports gracefully so test suites pass anywhere.
2. **Step 2 (Benchmark Completion)**: Create `benchmarks/scaling_test.py` (Experiment 3: Replica Scaling) to complete the 3 scientific evaluation experiments promised in the README.
3. **Step 3 (Observability Stack)**: Add Prometheus scrape configuration and Grafana service definition in `docker-compose.yml`.
4. **Step 4 (Frontend Usability)**: Add source code editing/version bumping in the web dashboard catalog.
