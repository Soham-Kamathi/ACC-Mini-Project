# Project Context & Technical Architecture Guide
## Kubernetes-Based Docker Serverless (FaaS) Function Execution Platform

> **Purpose of this Document:**  
> This file serves as a comprehensive, authoritative context document designed to be ingested by a Large Language Model (LLM) or developer. It encapsulates the complete idea, motivation, technology stack, system architecture, component interactions, security model, and functional workflows of the project.

---

## 1. Executive Summary & Project Vision

### 1.1 What is this Project?
This project is an enterprise-grade, self-hosted **Function-as-a-Service (FaaS)** execution platform (conceptually similar to a private implementation of **AWS Lambda**, **Google Cloud Functions**, or **OpenFaaS**). 

The platform allows developers to write event-driven functions (e.g., `def handler(event): ...`), deploy them via a web UI or REST API, and receive secure, auto-scaling HTTP endpoints. Behind the scenes, the platform automates the entire lifecycle:
- Packages raw code and dependencies into standardized Docker images.
- Pushes images to a container registry.
- Deploys and manages workloads on **Kubernetes (k8s)** using custom controllers.
- Scales functions dynamically under load and **scales idle functions down to zero (Scale-to-Zero)** to eliminate idle resource consumption.
- Performs on-demand **cold-start provisioning** when dormant functions receive traffic.
- Collects granular execution telemetry (cold vs. warm latency breakdowns, memory/CPU usage, Prometheus metrics).
- Exposes stable, obfuscated public invocation endpoints protected by scoped API keys and public internet tunneling (via Ngrok).

### 1.2 The Core Problem Solved
In traditional cloud architectures, microservices run continuously inside dedicated virtual machines or long-running containers. When idle, these servers consume CPU, memory, and energy. Serverless computing solves this by decoupling code execution from persistent infrastructure.

This project implements that abstraction from scratch:
1. **Developer Experience:** The developer only submits business logic and configuration (memory, CPU, timeout). They never write a Dockerfile, configure a Kubernetes Service/Deployment YAML, or manage ingress networking.
2. **Resource Efficiency:** The custom **FaaS Controller** monitors traffic and reaps idle containers down to zero replicas. When an invocation request arrives, it boots the container on-demand, dispatches the event, and resumes idle countdown.
3. **Multi-Tenant Security:** Strong tenant isolation ensures that user code executes inside hardened, non-root, read-only Kubernetes Pods, with scoped API keys and DNS-safe naming.

---

## 2. Technology Stack & Rationale

| Layer / Component | Technology | Role & Justification |
| :--- | :--- | :--- |
| **API Gateway & Controller** | **FastAPI (Python 3.10+)** | High-throughput asynchronous REST gateway, native OpenAPI/Swagger schema generation, Pydantic validation, and background lifespan tasks. |
| **ASGI Web Server** | **Uvicorn** | Lightning-fast ASGI web server hosting the FastAPI backend. |
| **Container Engine** | **Docker & Docker SDK for Python** | Builds isolated, lightweight Linux container images containing user code, packages, and the runtime runner. |
| **Container Registry** | **Docker Registry v2 (Local/Private)** | In-cluster/local OCI-compliant registry (`localhost:5000`) for versioned image storage without third-party cloud dependencies. |
| **Container Orchestrator** | **Kubernetes (k8s / Docker Desktop)** | Manages Pod scheduling, Deployments, ClusterIP Services, rolling updates, node resource limits, and health probes. |
| **Database & ORM** | **PostgreSQL 15 + SQLAlchemy 2.0** | Relational metadata store for users, functions, version history, API keys, and invocation logs. Features an automatic SQLite fallback for lightweight local dev. |
| **Security & Cryptography** | **Passlib (Bcrypt) & Python-Jose (JWT)** | Passwords hashed with salt via Bcrypt; administrative endpoints guarded by JSON Web Tokens. Public keys hashed with SHA-256. |
| **Frontend Web Dashboard** | **React 18 + Vite + Tailwind CSS** | Reactive, modern single-page dashboard featuring live code editing, deployment forms, real-time invocation tester, and dynamic integration code generation. |
| **Observability & Metrics** | **Prometheus Client (`prometheus-client`)** | Real-time time-series telemetry exporter (`/api/v1/metrics`) recording invocation counts, cold/warm durations, and active replicas. |
| **Public Networking** | **Ngrok / Cloudflare Tunnels** | Creates secure public ingress to the local cluster, enabling external webhooks, IoT devices, or remote microservices to invoke functions. |
| **Benchmarking & Testing** | **Pytest, HTTPX, Asyncio Load Testers** | Automated test suite and scientific benchmark experiments measuring cold vs. warm start latencies, concurrency limits, and autoscaling response curves. |

---

## 3. High-Level Architecture & Interaction Diagram

```text
                               +--------------------------------------------+
                               |          External Developer / Client       |
                               |    (React Dashboard, cURL, Python, Web)    |
                               +---------------------+----------------------+
                                                     |
                                                     | HTTPS / REST (JWT or X-API-Key)
                                                     v
                               +--------------------------------------------+
                               |        FastAPI Gateway Layer (:8000)       |
                               |  - /api/v1/auth    - /api/v1/functions     |
                               |  - /api/v1/invoke  - /api/v1/f/{public_id}  |
                               +---------------------+----------------------+
                                                     |
                       +-----------------------------+-----------------------------+
                       |                             |                             |
                       v                             v                             v
         +---------------------------+ +---------------------------+ +---------------------------+
         |     PostgreSQL Database   | |     FaaS Controller       | |    Prometheus Metrics     |
         | (Users, Functions, Keys,  | | - Inactivity Reaper Loop  | | (/api/v1/metrics)         |
         |  Versions, Telemetry Logs)| | - Reactive Autoscaler     | | Latency histograms, cold  |
         +---------------------------+ +-------------+-------------+ | start counters, replicas  |
                                                     |               +---------------------------+
                       +-----------------------------+-----------------------------+
                       |                                                           |
                       v                                                           v
         +---------------------------+                               +---------------------------+
         |   Docker Image Builder    |                               |  Kubernetes Orchestrator  |
         | - Docker SDK              |                               | - Namespace: faas-fn      |
         | - handler.py + server.py  |                               | - Deployments & Services  |
         +-------------+-------------+                               +-------------+-------------+
                       |                                                           |
                       | Pushes Built Image                                        | Pulls Image & Runs
                       v                                                           v
         +---------------------------+                               +---------------------------+
         |   Private Docker Registry | ============================> |     Function Pod (k8s)    |
         |      (localhost:5000)     |                               | +-----------------------+ |
         +---------------------------+                               | | Container (Port 8080) | |
                                                                     | | - Python 3.11 Runtime | |
                                                                     | | - server.py wrapper   | |
                                                                     | | - user handler.py     | |
                                                                     | +-----------------------+ |
                                                                     +---------------------------+
```

---

## 4. End-to-End System Workflow

### 4.1 Step 1: User Authentication & Multi-Tenant Isolation
1. **Registration & Login:** Users register at `POST /api/v1/auth/register` and authenticate via `POST /api/v1/auth/login`. Passwords are encrypted with Bcrypt. A signed JWT containing `sub: <user_id>` is issued.
2. **Tenant Scoping:** All functions belong to an `owner_id`. Uniqueness is enforced on `(owner_id, function_name)`. Thus, two separate tenants can both register a function named `data-processor` without namespace collisions.

### 4.2 Step 2: Function Registration & Automated Containerization
1. **Creation:** A developer submits Python code, package dependencies, memory/CPU quotas, execution timeout, and autoscaling thresholds to `POST /api/v1/functions/`.
2. **Initial State:** FastAPI persists the function in PostgreSQL with status `CREATING` and allocates version `v1`.
3. **Build Pipeline (`BuilderService`):**
   - Allocates an isolated temporary directory.
   - Writes user code to `handler.py` and dependencies to `requirements.txt`.
   - Injects the standardized platform runtime server (`server.py`) and `Dockerfile.template`.
   - Triggers `docker.build` via Docker SDK, producing image `localhost:5000/<username>/<function-name>:v1`.
   - Pushes the image to the local Docker Registry.
4. **Kubernetes Workload Provisioning (`K8sService`):**
   - Deploys a Kubernetes **Deployment** and **ClusterIP Service** in the `faas-fn` namespace.
   - Resource naming follows a strict DNS-1123 convention: `fn-<owner_id>-<func_name>-<version_tag>`.
   - Updates status to `READY` once the initial Pod passes readiness checks.

### 4.3 Step 3: Idle Reaper & Scale-to-Zero
1. **Background Daemon:** When FastAPI boots, `FaasController` initializes two background asyncio tasks: the **Inactivity Reaper** and the **Autoscaler**.
2. **Reaping Logic:** Every 10 seconds, the reaper checks all functions where `min_replicas == 0`.
3. If `(current_time - last_invoked_at) > 60 seconds` (configurable `IDLE_TIMEOUT_SECONDS`), the controller commands Kubernetes:
   ```python
   k8s.scale_deployment(deployment_name, replicas=0)
   ```
4. Function state transitions to `SCALED_TO_ZERO`. Compute resources are reclaimed by the cluster.

### 4.4 Step 4: Invocation Routing, Cold Starts & Warm Executions
When an invocation arrives (`POST /api/v1/invoke/{name}` or `POST /api/v1/f/{public_id}`):
1. **Routing:** `RouterService` resolves the function and selects the latest active/ready version (or pinned version).
2. **Cold Start Branch (`active_replicas == 0`):**
   - Records start timestamp $t_0$.
   - Commands Kubernetes to scale the deployment to 1 replica.
   - Polls the container's readiness endpoint (`http://<pod_ip>:8080/healthz`) until HTTP 200 is returned.
   - Computes cold-start latency:
     $$\text{duration}_{\text{cold\_start}} = (t_{\text{ready}} - t_0) \times 1000\text{ ms}$$
   - Increments Prometheus counter `faas_cold_starts_total`.
3. **Warm Start Branch (`active_replicas >= 1`):**
   - Pod is already running and ready in memory.
   - $\text{duration}_{\text{cold\_start}} = 0.0\text{ ms}$.
4. **Execution Dispatch:**
   - Gateway forwards the JSON event to the internal container endpoint: `POST http://<service_name>:8080/execute`.
   - Inside the container, `server.py` delegates to `handler(event)` in an isolated thread worker with timeout enforcement.
   - Returns result payload, status code, and container execution duration ($\text{duration}_{\text{exec}}$).
5. **Auditing & Telemetry:**
   - Gateway computes total latency:
     $$\text{duration}_{\text{total}} = \text{duration}_{\text{cold\_start}} + \text{duration}_{\text{exec}}$$
   - Writes an `InvocationLog` record (UUID request ID, inputs, outputs, timings, cold start flag, execution mode).
   - Updates Prometheus histograms (`faas_invocation_duration_seconds`).

### 4.5 Step 5: Concurrency-Based Autoscaling
1. Each function defines:
   - `min_replicas`: Lower bound (default: `0`, enabling scale-to-zero).
   - `max_replicas`: Upper bound (ceiling: up to `20`).
   - `target_concurrency`: In-flight requests allocated per container Pod (default: `5`).
2. **Algorithm:** Every 2 seconds, the autoscaler evaluates in-flight concurrency per version:
   $$\text{desired\_replicas} = \left\lceil \frac{\text{in\_flight\_requests}}{\text{target\_concurrency}} \right\rceil$$
   $$\text{target} = \max(\text{min\_replicas}, \min(\text{desired\_replicas}, \text{max\_replicas}))$$
3. **Scale-Up:** Instantaneous reaction based on peak load within the window.
4. **Scale-Down Stabilization:** To avoid replica flapping during momentary dips, scale-down applies a 30-second stabilization dampening window (`SCALE_DOWN_STABILIZATION_SECONDS`).

---

## 5. Security & Isolation Architecture

### 5.1 Pod Security Hardening
User functions execute untrusted, arbitrary code. The platform enforces defense-in-depth at the Kubernetes Pod level:
- `runAsNonRoot: true`: Prevents processes from running as root.
- `runAsUser: 10001`: Forces a dedicated unprivileged UID.
- `readOnlyRootFilesystem: true`: Prevents attackers or scripts from modifying container binaries.
- `capabilities: { drop: ["ALL"] }`: Revokes all Linux kernel capabilities.
- `allowPrivilegeEscalation: false`: Denies privilege escalation (`setuid`).
- `automountServiceAccountToken: false`: Pods cannot interact with the Kubernetes API server.
- `tmp volume`: An ephemeral `emptyDir` mounted at `/tmp` with a strict `64Mi` memory cap.
- `resource quotas`: Mandatory CPU and Memory limits (e.g., `256Mi` RAM, `500m` CPU) to prevent noisy neighbor starvation.

### 5.2 Public Invocations & Scoped API Keys
- **Stable Public Endpoints:** Functions expose `POST /api/v1/f/{public_id}`, decoupling the external invocation URL from user account credentials or internal database IDs.
- **One-Way Hashing:** API keys (prefix `fk_...`) are generated with high entropy and stored exclusively as **SHA-256 hashes**. The plaintext key is shown only once at generation time.
- **Granular Scoping:** Keys can be labeled, revoked, and pinned to a specific version (e.g. `v1`).
- **Rate Limiting:** In-memory sliding window / token bucket enforces a 120 requests/minute limit per API key.
- **Payload Guardrails:** Default 1 MB request payload cap to defend against buffer overflow and DoS attacks.

### 5.3 Execution Boundary Enforcement
- **Default Behavior:** User code executes strictly inside a Kubernetes Pod. In-process `exec()` is explicitly disabled.
- **Safe Fallback Flag (`ALLOW_LOCAL_SANDBOX`):** Only when set to `true` in local non-cluster development does the backend run code in a local Python sandbox. Every response headers and database log explicitly identifies the runtime environment (`executed_on: "k8s"` vs `"sandbox"`).

---

## 6. Standard Container Runtime: `server.py`

Every packaged function image incorporates a standardized lightweight HTTP runtime (`backend/runtimes/python311/server.py`) that wraps the developer's `handler.py`.

### Endpoints exposed by the container (Port 8080):
- `GET /healthz`: Kubernetes liveness and readiness probe endpoint. Returns `{"status": "ok"}` once user modules are imported and ready.
- `POST /execute`: Invocation endpoint.
  - Parses JSON request body.
  - Dynamically invokes `handler(event)` or `main(event)`.
  - Enforces the user's timeout constraint via thread execution pools.
  - Catches user exceptions and returns structured error traces with HTTP status codes:
    - `200 OK`: Successful execution with result payload and elapsed execution time.
    - `400 Bad Request`: Malformed event JSON.
    - `500 Internal Server Error`: Unhandled runtime exceptions inside user code.
    - `504 Gateway Timeout`: Function exceeded allocated execution timeout limit.

---

## 7. Database Entity Relationship Model

```text
+------------------------------------+
|               User                 |
+------------------------------------+
| id: Integer (PK)                   |
| username: String (Unique)          |
| email: String (Unique)             |
| hashed_password: String            |
| created_at: DateTime               |
+-----------------+------------------+
                  | 1
                  |
                  | N
+-----------------v------------------+       1       N +------------------------------------+
|             Function               +----------------->               ApiKey               |
+------------------------------------+                 +------------------------------------+
| id: Integer (PK)                   |                 | id: Integer (PK)                   |
| public_id: String (Unique, Indexed)|                 | key_hash: String (SHA-256, Indexed)|
| name: String                       |                 | key_prefix: String (e.g. fk_live)  |
| owner_id: Integer (FK -> User.id)  |                 | function_id: Integer (FK)          |
| runtime: String (e.g. python311)   |                 | pinned_version_id: Integer (FK,Opt)|
| description: String                |                 | is_active: Boolean                 |
| status: Enum                       |                 | rate_limit_rpm: Integer (120)      |
| memory_limit: String (256Mi)       |                 +------------------------------------+
| cpu_limit: String (500m)           |
| timeout_seconds: Integer (10)      |
| min_replicas: Integer (0)          |
| max_replicas: Integer (5)          |
| target_concurrency: Integer (5)    |
| active_replicas: Integer           |
| last_invoked_at: DateTime          |
+-----------------+------------------+
                  | 1
                  |
                  | N
+-----------------v------------------+       1       N +------------------------------------+
|         FunctionVersion            +----------------->           InvocationLog            |
+------------------------------------+                 +------------------------------------+
| id: Integer (PK)                   |                 | id: Integer (PK)                   |
| function_id: Integer (FK)          |                 | request_id: String (UUID)          |
| version_tag: String (v1, v2...)    |                 | function_id: Integer (FK)          |
| code: Text                         |                 | version_id: Integer (FK)           |
| requirements: Text                 |                 | is_cold_start: Boolean             |
| image_tag: String                  |                 | cold_start_duration_ms: Float      |
| is_active: Boolean                 |                 | execution_duration_ms: Float       |
| created_at: DateTime               |                 | total_duration_ms: Float           |
|                                    |                 | status_code: Integer               |
|                                    |                 | executed_on: String (k8s/sandbox)  |
|                                    |                 | payload_input: Text                |
|                                    |                 | payload_output: Text               |
|                                    |                 | error_message: Text                |
|                                    |                 | timestamp: DateTime                |
+------------------------------------+                 +------------------------------------+
```

---

## 8. Complete REST API Specifications

### 8.1 Authentication (`/api/v1/auth`)
- `POST /register`: Register a new developer account. Body: `{ username, email, password }`.
- `POST /login`: Authenticate credentials. Returns: `{ access_token, token_type: "bearer" }`.
- `GET /me`: Returns details of the currently authenticated developer.

### 8.2 Function Lifecycle Management (`/api/v1/functions`)
- `GET /`: List all functions owned by the authenticated tenant.
- `POST /`: Create and deploy a new function. Compiles image and generates K8s deployment.
- `GET /{name}`: Retrieve full metadata, resource quotas, and version history.
- `PUT /{name}`: Update function code, settings, or deploy a new version (`v2`, `v3`).
- `DELETE /{name}`: Delete a function, tear down its K8s Deployment/Service, and clean DB.
- `GET /{name}/scaling`: Live inspection of autoscaler status (min/max replicas, live ready pods, desired pods).

### 8.3 Invocations (`/api/v1/invoke` and `/api/v1/f`)
- `POST /invoke/{name}`: Invoke the latest ready version of an owned function (requires JWT).
- `POST /invoke/{name}/{version}`: Invoke a specific pinned version (e.g. `v1`).
- `POST /f/{public_id}`: External public invocation route. Authenticated via `X-API-Key` header or JWT.
- `POST /f/{public_id}/{version}`: External invocation pinned to a specific version.

### 8.4 Scoped API Keys (`/api/v1/keys`)
- `GET /function/{function_id}`: List all active and revoked API keys for a function.
- `POST /function/{function_id}`: Generate a new SHA-256 hashed API key (with optional version pinning).
- `DELETE /{key_id}`: Revoke an existing API key immediately.

### 8.5 Observability & Logs (`/api/v1/logs` & `/api/v1/metrics`)
- `GET /logs/{function_id}`: Paginated history of invocations (timings, payloads, errors).
- `GET /logs/{function_id}/stats`: Aggregated summary (cold-start percentage, avg execution duration, total invocations).
- `GET /metrics`: Standard Prometheus metrics scrape target.

### 8.6 Cluster Telemetry (`/api/v1/cluster`)
- `GET /status`: Inspects Kubernetes cluster connectivity, node status, and namespace health.

---

## 9. Web Dashboard Features (Frontend)

The frontend is a single-page application built with **React 18**, **TypeScript**, **Vite**, and **Tailwind CSS**.

### Key Modules:
1. **Catalog & Overview:** Real-time cards displaying deployed functions, live replica counts, status pills (`READY`, `BUILDING`, `SCALED_TO_ZERO`), and resource allocations.
2. **Interactive Code Editor:** In-browser code editing with syntax highlighting and pre-built templates (*Hello World*, *Fibonacci Benchmark*, *JSON Data Processing*).
3. **Live Invocation Console:** JSON event payload editor allowing instant testing with real-time feedback:
   - Output payload viewer.
   - Status badge (e.g. 200 OK, 504 Timeout).
   - Cold vs. Warm latency meter (visualizing container startup vs. compute duration).
4. **API Access & Snippet Generator (`ApiAccessPanel.tsx`):**
   - Manage function-scoped API keys (generate, view prefix, revoke).
   - **Dynamic Integration Snippets:** Live formatted cURL, Python `requests`, and Node.js fetch code samples that automatically update with the active public domain, API key, and whatever JSON payload is currently typed into the event editor.
   - Incorporates the `ngrok-skip-browser-warning: true` header to bypass Ngrok free-tier interstitials programmatically.
5. **Observability Dashboard:** Graphs and metrics showing cold-start ratios, latency percentiles, and historical invocation logs.

---

## 10. Automated Benchmarking & Scientific Experiments

The repository includes a dedicated benchmark suite under `benchmarks/` to validate FaaS performance under academic conditions:

### 10.1 Experiment 1: Cold Start vs. Warm Start Latency (`cold_start_test.py`)
- Forces a function into `SCALED_TO_ZERO` state.
- Executes an initial invocation, precisely measuring the cold-start delay (Pod scheduling + image pull + container initialization).
- Immediately follows with sequential warm invocations to quantify the warm execution baseline and compute the cold-start penalty multiplier.

### 10.2 Experiment 2: Concurrency & Throughput (`concurrency_test.py`)
- Employs asynchronous workers (`asyncio` / `httpx`) to simulate 1, 10, 50, and 100 concurrent clients.
- Measures Requests Per Second (RPS), error rates, and p50, p90, p95, p99 latency distributions.

### 10.3 Experiment 3: Replica Scaling & Autoscaling Dynamics (`scaling_test.py`)
- **Part A (Fixed Scaling):** Benchmarks performance across static replica counts (1, 2, 5, 10 Pods) under constant load.
- **Part B (Dynamic Autoscaling):** Applies burst load to trigger reactive scale-up, verifies traffic distribution across Pods, and records scale-down stabilization behavior after load subsides.

---

## 11. One-Click Startup & Deployment Flow

The project is structured for zero-friction local deployment:

### Launch Script (`start-all.ps1` / `start-all.bat`):
1. Verifies that **Docker Desktop** (with Kubernetes enabled) is running.
2. Initializes `.env` configuration from `.env.example`.
3. Boots PostgreSQL and Docker Registry via `docker compose up -d`.
4. Spawns the FastAPI backend inside a Python virtual environment on port `8000`.
5. Launches the React/Vite development server on port `5173`.
6. (Optional) Starts an **Ngrok Tunnel** on port `5173` (with Vite reverse-proxying `/api/*` to FastAPI), exposing both UI and APIs to the public internet under a unified domain.

---

## 12. Instructions & Invariants for LLMs Assisting this Project

When writing code, refactoring, or generating features for this codebase:
1. **Preserve Isolation:** Never execute untrusted user code inside the FastAPI backend process in production mode. Execution must always dispatch to the Kubernetes Pod runtime via `RouterService`.
2. **K8s Naming Constraints:** All Kubernetes Deployment and Service names must conform strictly to RFC 1123 DNS label standards (`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`, max 63 characters). Always use `backend.app.services.naming.get_deployment_name(...)`.
3. **Security Invariants:**
   - Never store plain text API keys. Store only SHA-256 hashes.
   - Maintain the Pod security context (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `drop: ["ALL"]`).
4. **Autoscaling Invariants:** Scale-up must be responsive to burst load, but scale-down must respect the stabilization window (`SCALE_DOWN_STABILIZATION_SECONDS`) to avoid container flapping. Scale-to-zero must only activate when `min_replicas == 0` and idle duration exceeds `IDLE_TIMEOUT_SECONDS`.
5. **Database Transactions:** Always use scoped SQLAlchemy database sessions (`get_db`) with proper commit/rollback handling and model serialization.
