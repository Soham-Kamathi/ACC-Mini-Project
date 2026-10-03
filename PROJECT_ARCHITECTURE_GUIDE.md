# Comprehensive System Architecture & Codebase Guide
## Kubernetes-Based Docker Serverless (FaaS) Function Execution Platform

---

## 1. Executive Summary & Project Purpose

The **Kubernetes-Based Docker Serverless Function Execution Platform** is a self-hosted **Function-as-a-Service (FaaS)** system inspired by AWS Lambda, Google Cloud Functions, and OpenFaaS. 

Traditional serverless platforms abstract away infrastructure management, allowing developers to simply write a function (e.g. `def handler(event): ...`) and receive an HTTP endpoint. Behind the scenes, the platform must dynamically build execution environments, orchestrate containers, manage cold starts, automatically scale idle services down to zero, enforce strict CPU/memory resource limits, and collect observability metrics.

This project implements that entire platform layer from scratch using:
1. **FastAPI** as the API Gateway and management REST interface.
2. **Docker** as the standardized runtime containerization mechanism.
3. **A Local/Private Docker Registry** to store packaged function images.
4. **Kubernetes** as the container orchestrator managing Deployments, Services, Pods, and scaling.
5. **A Custom FaaS Controller Daemon** that implements a scale-to-zero reaper and an on-demand cold-start provisioner.
6. **PostgreSQL / SQLAlchemy** as the persistent function metadata and execution telemetry registry.
7. **Prometheus & Grafana** for metrics collection and real-time observability.
8. **React + Vite + Tailwind CSS** as an interactive web dashboard with an in-browser code editor and live invocation tester.
9. **Automated Benchmarking Suite** to scientifically evaluate cold vs. warm start latencies and concurrent request throughput.

---

## 2. High-Level System Architecture & Component Interaction

```
                                  +---------------------------------------+
                                  |        Web Browser / Developer        |
                                  |     (React + Vite + Tailwind CSS)     |
                                  +-------------------+-------------------+
                                                      |
                                                      | HTTP / REST (JWT Auth)
                                                      v
                                  +---------------------------------------+
                                  |        FastAPI API Gateway Layer      |
                                  |      (/api/v1/functions, /invoke)     |
                                  +-------------------+-------------------+
                                                      |
                        +-----------------------------+-----------------------------+
                        |                             |                             |
                        v                             v                             v
           +-------------------------+   +-------------------------+   +-------------------------+
           |     PostgreSQL / DB     |   |      FaaS Controller    |   |    Prometheus Metrics   |
           | (Users, Functions, Logs)|   |  (Scale-to-Zero Daemon) |   |  (/api/v1/metrics)      |
           +-------------------------+   +------------+------------+   +-------------------------+
                                                      |
                        +-----------------------------+-----------------------------+
                        |                                                           |
                        v                                                           v
           +-------------------------+                                 +-------------------------+
           |   Docker Image Builder  |                                 | Kubernetes Orchestrator |
           |  (Docker SDK + Wrapper) |                                 | (Deployments, Services) |
           +------------+------------+                                 +------------+------------+
                        |                                                           |
                        | Pushes Image                                              | Pulls Image & Runs
                        v                                                           v
           +-------------------------+                                 +-------------------------+
           |  Private Docker Registry| ==============================> |   Function Pod (k8s)    |
           |    (localhost:5000)     |                                 | +---------------------+ |
           +-------------------------+                                 | | Docker Container    | |
                                                                       | | (Python 3.11 Runtime| |
                                                                       | |  handler.py wrapper)| |
                                                                       | +---------------------+ |
                                                                       +-------------------------+
```

---

## 3. Technology Stack & Rationale

| Layer / Component | Technology | Purpose & Rationale |
| :--- | :--- | :--- |
| **API Gateway & Backend** | **FastAPI (Python 3.10+)** | High performance, asynchronous request handling, automatic OpenAPI/Swagger documentation, and native Pydantic validation. |
| **Container Engine** | **Docker & Docker SDK** | Provides lightweight, isolated Linux containers packaging the user's function and third-party dependencies. |
| **Container Registry** | **Docker Registry v2** | Local registry hosting built function images (`localhost:5000/user/func:v1`) without relying on external cloud registries. |
| **Orchestrator** | **Kubernetes (k8s)** | Handles Pod scheduling, self-healing, internal networking (ClusterIP Services), resource limits, and replica scaling. |
| **Database & ORM** | **PostgreSQL & SQLAlchemy** | Stores relational metadata: user credentials, function configurations, versions, resource limits, and invocation telemetry logs. (Includes SQLite fallback for standalone local development). |
| **Security & Auth** | **JWT (JSON Web Tokens) & Passlib (Bcrypt)** | Secures API endpoints, enforces authentication, and isolates function ownership across tenants. |
| **Frontend UI** | **React 18 + Vite + Tailwind CSS** | Provides a responsive, real-time dashboard for function creation, live code editing, invocation testing, log streaming, and metric inspection. |
| **Observability** | **Prometheus Client** | Tracks invocations, error rates, cold starts, and latency histograms for scientific performance evaluation. |
| **Testing & Benchmarks**| **Pytest, HTTPX, Locust/Asyncio** | Automated unit tests and load generation scripts measuring cold vs. warm start latency and concurrency throughput. |

---

## 4. End-to-End Workflow & Function Lifecycle

### Step 1: User Registration & Authentication
1. Developer creates an account via `POST /api/v1/auth/register` or logs in via `POST /api/v1/auth/login`.
2. The server hashes the password with **Bcrypt** and returns a signed **JWT Access Token**.
3. All subsequent management requests include `Authorization: Bearer <token>`.

### Step 2: Function Registration & Dynamic Image Build
1. The developer submits function code (e.g. `def handler(event): ...`), runtime (`python311`), resource limits (`memory: 256Mi`, `cpu: 500m`), and execution timeout (`10s`) via `POST /api/v1/functions/`.
2. The API Gateway creates a record in PostgreSQL with status `CREATING` and version `v1`.
3. An asynchronous background task invokes `BuilderService`:
   - Creates a clean temporary build directory.
   - Writes the user's code to `handler.py` and dependencies to `requirements.txt`.
   - Copies the standardized runtime server (`server.py`) and `Dockerfile.template`.
   - Executes `docker build` using the Docker SDK to compile a production image: `localhost:5000/{username}/{function_name}:v1`.
   - Pushes the image to the local Docker Registry.
4. `K8sService` generates a Kubernetes **Deployment** and **ClusterIP Service** in the `faas-fn` namespace.
5. The function status transitions to `READY`.

### Step 3: Scale-to-Zero (Inactivity Reaper Daemon)
1. In a serverless platform, keeping idle containers running wastes CPU and RAM.
2. The `FaasController` runs a background reaper task every 10 seconds (`_reaper_loop`).
3. If a function has received no invocation requests for $>60$ seconds (`IDLE_TIMEOUT_SECONDS`), the controller calls Kubernetes API to scale deployment replicas to **0** (`spec.replicas = 0`).
4. The function status is updated in PostgreSQL to `SCALED_TO_ZERO`.

### Step 4: Invocation Routing & Cold-Start Provisioning
When a user calls `POST /api/v1/invoke/{name}`:
1. `RouterService` inspects the function's state in PostgreSQL and Kubernetes.
2. **Case A: Cold Start (`replicas == 0` or `status == SCALED_TO_ZERO`)**:
   - The router records the exact start timestamp `t0`.
   - Triggers `K8sService.scale_deployment(name, 1)`.
   - Kubernetes schedules the Pod, pulls the container image, starts the container, and runs the runtime wrapper.
   - The router polls the Pod's readiness probe (`/healthz` endpoint on port 8080) until healthy.
   - Calculates `cold_start_duration_ms = (t_ready - t0) * 1000`.
   - Increments Prometheus counter `faas_cold_starts_total`.
3. **Case B: Warm Start (`replicas >= 1`)**:
   - The container is already active and ready in memory.
   - `cold_start_duration_ms = 0.0`.
4. **Execution**:
   - The router sends the JSON event payload to the container's internal endpoint: `http://<pod_ip>:8080/execute`.
   - The container's `server.py` executes `handler(event)` within a worker thread enforcing the user's timeout.
   - Returns the result, execution duration `execution_duration_ms`, and status code.
5. **Telemetry & Logging**:
   - `total_duration_ms = cold_start_duration_ms + execution_duration_ms`.
   - Records an `InvocationLog` entry in PostgreSQL.
   - Updates Prometheus metric `faas_invocation_duration_seconds{type="cold"|"warm"}`.
   - Returns structured JSON response to the caller.

---

## 5. Detailed File-by-File Breakdown

Below is the exhaustive catalog of every file in the codebase, detailing its exact purpose, exported interfaces, and operational mechanics.

### 5.1 Root Configuration & Supporting Infrastructure

#### 1. [`docker-compose.yml`](file:///d:/ACC%20Mini%20Project/docker-compose.yml)
- **Purpose**: Provisions local infrastructure dependencies with zero manual setup.
- **Services Defined**:
  - `postgres`: PostgreSQL 15 Alpine database on port `5432` with persistent volume `postgres_data`.
  - `registry`: Private Docker Registry v2 on port `5000` with volume `registry_data` for storing built function images.
- **Healthchecks**: Uses `pg_isready` to ensure database readiness before connections are accepted.

#### 2. [`README.md`](file:///d:/ACC%20Mini%20Project/README.md)
- **Purpose**: Quickstart guide for developers, summarizing system architecture, installation steps, and CLI commands to start backend, frontend, and benchmarks.

---

### 5.2 Backend Core & Database (`backend/app/core/`)

#### 3. [`backend/app/core/config.py`](file:///d:/ACC%20Mini%20Project/backend/app/core/config.py)
- **Purpose**: Centralized application configuration powered by Pydantic's `BaseSettings` and `SettingsConfigDict`.
- **Key Parameters**:
  - `API_V1_STR`: `/api/v1` API prefix.
  - `SECRET_KEY` & `ALGORITHM`: Configuration for signing and verifying JWT tokens.
  - `DATABASE_URL`: PostgreSQL connection string with automatic fallback to SQLite (`sqlite:///./faas_metadata.db`).
  - `DOCKER_REGISTRY`: Target registry host (`localhost:5000`).
  - `K8S_NAMESPACE`: Kubernetes namespace for serverless function pods (`faas-fn`).
  - `IDLE_TIMEOUT_SECONDS`: Threshold before an idle function is scaled down to 0 replicas (default: `60s`).
  - `REAPER_INTERVAL_SECONDS`: Frequency of the background reaper sweep (default: `10s`).

#### 4. [`backend/app/core/db.py`](file:///d:/ACC%20Mini%20Project/backend/app/core/db.py)
- **Purpose**: Database session management and table initialization.
- **Key Functions**:
  - `create_engine(...)`: Sets up connection pooling for PostgreSQL / SQLite.
  - `SessionLocal`: Scoped session factory for database transactions.
  - `get_db()`: FastAPI dependency yielding database sessions with automatic cleanup (`db.close()`).
  - `init_db()`: Programmatically discovers all SQLAlchemy models and creates missing tables (`Base.metadata.create_all`).

#### 5. [`backend/app/core/security.py`](file:///d:/ACC%20Mini%20Project/backend/app/core/security.py)
- **Purpose**: Cryptographic security, password hashing, and authentication token handling.
- **Key Functions**:
  - `verify_password(plain, hashed)`: Verifies plaintext passwords against Bcrypt hashes.
  - `get_password_hash(password)`: Generates salted Bcrypt password hashes.
  - `create_access_token(subject, expires_delta)`: Creates signed JWT tokens carrying user IDs.
  - `get_current_user_id(token)`: FastAPI dependency that decodes JWT bearer tokens, validates expiry/signatures, and returns the authenticated user ID.

---

### 5.3 Database Models (`backend/app/models/`)

#### 6. [`backend/app/models/user.py`](file:///d:/ACC%20Mini%20Project/backend/app/models/user.py)
- **Purpose**: Represents registered developers/tenants on the platform.
- **Fields**: `id`, `username` (unique index), `email` (unique index), `hashed_password`, `created_at`.
- **Relationships**: `functions` (1-to-many relationship with cascading delete).

#### 7. [`backend/app/models/function.py`](file:///d:/ACC%20Mini%20Project/backend/app/models/function.py)
- **Purpose**: Defines function metadata, resource quotas, and version history.
- **Models**:
  - `Function`:
    - `name`: Lowercase identifier (e.g. `calc-fibonacci`).
    - `owner_id`: Foreign key referencing `users.id`.
    - `runtime`: e.g. `python311`.
    - `status`: State machine enum: `CREATING`, `BUILDING`, `READY`, `RUNNING`, `IDLE`, `SCALED_TO_ZERO`, `ERROR`.
    - `memory_limit` / `cpu_limit`: Kubernetes resource limits (e.g. `256Mi`, `500m`).
    - `timeout_seconds`: Execution timeout.
    - `active_replicas`: Number of live running pods.
    - `last_invoked_at`: Timestamp of the most recent invocation.
  - `FunctionVersion`:
    - `function_id`: Foreign key referencing parent `functions.id`.
    - `version_tag`: Version identifier (e.g. `v1`, `v2`).
    - `code`: Full Python source code.
    - `requirements`: Pinned pip dependencies.
    - `image_tag`: Built Docker image URI (`localhost:5000/user/func:v1`).
    - `is_active`: Flag denoting active deployment version.

#### 8. [`backend/app/models/invocation.py`](file:///d:/ACC%20Mini%20Project/backend/app/models/invocation.py)
- **Purpose**: Granular execution audit and performance telemetry logging.
- **Fields**:
  - `request_id`: UUID for request tracing.
  - `function_id` / `version_id`: Target function and version.
  - `is_cold_start`: Boolean indicating whether container spin-up occurred.
  - `cold_start_duration_ms`: Time taken to scale up and ready the Pod in milliseconds.
  - `execution_duration_ms`: Duration spent executing `handler(event)` inside the container.
  - `total_duration_ms`: Combined end-to-end latency.
  - `status_code`: HTTP response status code (e.g. `200`, `500`, `504`).
  - `payload_input` / `payload_output` / `error_message`: Request/Response JSON payloads and error stack traces.
  - `timestamp`: Event timestamp.

#### 9. [`backend/app/models/__init__.py`](file:///d:/ACC%20Mini%20Project/backend/app/models/__init__.py)
- **Purpose**: Exports all database models (`User`, `Function`, `FunctionVersion`, `InvocationLog`) for clean imports across the backend.

---

### 5.4 Schemas & DTOs (`backend/app/schemas/`)

#### 10. [`backend/app/schemas/auth.py`](file:///d:/ACC%20Mini%20Project/backend/app/schemas/auth.py)
- **Purpose**: Pydantic schemas for authentication requests and responses: `UserCreate`, `UserLogin`, `UserOut`, and `Token`.

#### 11. [`backend/app/schemas/function.py`](file:///d:/ACC%20Mini%20Project/backend/app/schemas/function.py)
- **Purpose**: Pydantic validation schemas for function operations:
  - `FunctionCreate`: Validates function name regex (`^[a-z0-9-]+$`), code, runtime, and memory/CPU limits.
  - `FunctionUpdate`: Partial update payload for code, resource limits, and version bumping.
  - `FunctionOut` / `FunctionDetailOut`: Response schemas with serialized status and version histories.

#### 12. [`backend/app/schemas/invocation.py`](file:///d:/ACC%20Mini%20Project/backend/app/schemas/invocation.py)
- **Purpose**: Schemas for function execution: `InvokeRequest` (JSON event payload), `InvokeResponse` (result + latency breakdown), and `InvocationLogOut`.

#### 13. [`backend/app/schemas/__init__.py`](file:///d:/ACC%20Mini%20Project/backend/app/schemas/__init__.py)
- **Purpose**: Exports all schemas for unified import.

---

### 5.5 Backend Services Layer (`backend/app/services/`)

#### 14. [`backend/app/services/builder.py`](file:///d:/ACC%20Mini%20Project/backend/app/services/builder.py)
- **Purpose**: Automated Docker image packaging engine.
- **Key Class**: `BuilderService`
- **How It Works**:
  1. Initializes Docker client via `docker.from_env()`.
  2. In `build_function_image(...)`:
     - Creates an isolated temporary directory.
     - Writes user function code to `handler.py`.
     - Copies base runtime `server.py` and `Dockerfile.template` from `backend/runtimes/python311/`.
     - Invokes `docker.images.build(...)` to assemble the image.
     - Tags the image as `localhost:5000/{username}/{func_name}:{version_tag}`.
     - Optionally pushes the image to the local Docker registry.
     - Returns the final image URI.

#### 15. [`backend/app/services/k8s_client.py`](file:///d:/ACC%20Mini%20Project/backend/app/services/k8s_client.py)
- **Purpose**: Direct Kubernetes orchestration and lifecycle management via the official `kubernetes` Python SDK.
- **Key Class**: `K8sService`
- **Key Capabilities**:
  - `_init_client()`: Connects to in-cluster config or local kubeconfig (Docker Desktop / Minikube).
  - `_ensure_namespace(namespace)`: Verifies or creates the `faas-fn` namespace.
  - `deploy_function(...)`: Programmatically creates/updates a Kubernetes **Deployment** with:
    - Pod labels: `app: fn-{function_name}`.
    - Security context: `runAsNonRoot=True`, `runAsUser=10001`, `allowPrivilegeEscalation=False`, dropped Linux capabilities.
    - Resource requests (`64Mi`, `100m`) and limits (`256Mi`, `500m`).
    - Readiness probe checking `/healthz` on port 8080.
    - Accompanying **ClusterIP Service** routing port `8080`.
  - `scale_deployment(function_name, replicas)`: Dynamically adjusts deployment replica count (`spec.replicas = n`) to implement scale-to-zero and warm-up.
  - `wait_for_ready_pod(function_name, timeout)`: Polls Pod status until the container passes its readiness probe and returns the active Pod IP.
  - `delete_function(function_name)`: Removes Deployments and Services when a function is deleted.

#### 16. [`backend/app/services/controller.py`](file:///d:/ACC%20Mini%20Project/backend/app/services/controller.py)
- **Purpose**: Background daemon orchestrating function lifecycle and scale-to-zero.
- **Key Class**: `FaasController`
- **How It Works**:
  - `start()` / `stop()`: Managed by FastAPI's lifespan context manager.
  - `_reaper_loop()`: Asynchronous loop running every 10 seconds.
  - `check_idle_functions()`: Queries all functions where `active_replicas > 0`. If `(now - last_invoked_at) > IDLE_TIMEOUT_SECONDS`, executes `k8s_service.scale_deployment(fn.name, 0)` and updates database status to `SCALED_TO_ZERO`.

#### 17. [`backend/app/services/router.py`](file:///d:/ACC%20Mini%20Project/backend/app/services/router.py)
- **Purpose**: Invocation routing, on-demand cold-start provisioning, and Prometheus latency telemetry.
- **Key Class**: `RouterService`
- **Prometheus Metrics Defined**:
  - `faas_invocations_total{function_name, status}` (Counter).
  - `faas_cold_starts_total{function_name}` (Counter).
  - `faas_invocation_duration_seconds{function_name, type="cold"|"warm"}` (Histogram).
  - `faas_active_replicas{function_name}` (Gauge).
- **Execution Flow**:
  1. Detects whether target function is currently scaled to zero.
  2. If cold, scales deployment to 1, waits for readiness, and records exact cold-start duration.
  3. Dispatches HTTP POST request with event payload to container's `/execute` endpoint.
  4. Records execution latency, saves audit log in PostgreSQL, updates Prometheus histograms, and returns output.

---

### 5.6 API Endpoints & Routers (`backend/app/api/`)

#### 18. [`backend/app/api/auth.py`](file:///d:/ACC%20Mini%20Project/backend/app/api/auth.py)
- **Endpoints**:
  - `POST /api/v1/auth/register`: Creates new user account and returns JWT token.
  - `POST /api/v1/auth/login`: Authenticates OAuth2 form data and returns JWT token.
  - `GET /api/v1/auth/me`: Returns authenticated user profile.

#### 19. [`backend/app/api/functions.py`](file:///d:/ACC%20Mini%20Project/backend/app/api/functions.py)
- **Endpoints**:
  - `POST /api/v1/functions/`: Creates function, triggers background Docker image build and Kubernetes deployment.
  - `GET /api/v1/functions/`: Lists all functions owned by the authenticated user.
  - `GET /api/v1/functions/{name}`: Retrieves function details and full version history.
  - `PUT /api/v1/functions/{name}`: Updates code or resource limits, automatically incrementing version (`v2`, `v3`) and triggering a rebuild.
  - `DELETE /api/v1/functions/{name}`: Cleans up Kubernetes resources and deletes database records.

#### 20. [`backend/app/api/invoke.py`](file:///d:/ACC%20Mini%20Project/backend/app/api/invoke.py)
- **Endpoints**:
  - `POST /api/v1/invoke/{name}`: Invokes the latest active version of a function.
  - `POST /api/v1/invoke/{name}/{version}`: Invokes a specific version of a function.

#### 21. [`backend/app/api/logs.py`](file:///d:/ACC%20Mini%20Project/backend/app/api/logs.py)
- **Endpoints**:
  - `GET /api/v1/functions/{name}/logs`: Retrieves paginated invocation history for a function.
  - `GET /api/v1/logs/recent`: Retrieves the 20 most recent invocations across all user functions for the dashboard feed.

#### 22. [`backend/app/api/metrics.py`](file:///d:/ACC%20Mini%20Project/backend/app/api/metrics.py)
- **Endpoints**:
  - `GET /api/v1/metrics`: Standard Prometheus metrics scraping endpoint returning raw metric lines.
  - `GET /api/v1/stats`: Aggregated summary statistics for frontend dashboard KPI cards (total functions, active pods, cold-start count, cold-start ratio %, average latencies).

#### 23. [`backend/app/api/cluster.py`](file:///d:/ACC%20Mini%20Project/backend/app/api/cluster.py)
- **Endpoints**:
  - `GET /api/v1/cluster/status`: Reports real-time connectivity status of Kubernetes, Docker daemon, private registry, and the scale-to-zero reaper daemon.

#### 24. [`backend/app/main.py`](file:///d:/ACC%20Mini%20Project/backend/app/main.py)
- **Purpose**: Main FastAPI application entrypoint.
- **Mechanics**:
  - Manages application lifespan (`@asynccontextmanager`): initializes database tables and starts the `FaasController` background reaper on startup, gracefully stopping it on shutdown.
  - Configures CORS middleware allowing local frontend access.
  - Mounts all API routers under `/api/v1`.

---

### 5.7 Standardized Serverless Runtime (`backend/runtimes/python311/`)

#### 25. [`backend/runtimes/python311/server.py`](file:///d:/ACC%20Mini%20Project/backend/runtimes/python311/server.py)
- **Purpose**: In-container HTTP serverless execution wrapper.
- **Mechanics**:
  - Dynamically imports `handler.py` and inspects `handler(event)`.
  - Serves `GET /healthz` for Kubernetes readiness probes.
  - Serves `POST /execute`:
    - Receives input JSON payload.
    - Executes `user_handler(event)` in a worker thread.
    - Enforces timeout via `future.result(timeout=TIMEOUT_SECONDS)`.
    - Handles exceptions and returns structured JSON containing `{ "statusCode": 200, "result": ..., "execution_time_ms": ... }`.

#### 26. [`backend/runtimes/python311/Dockerfile.template`](file:///d:/ACC%20Mini%20Project/backend/runtimes/python311/Dockerfile.template)
- **Purpose**: Base container definition for Python 3.11 functions.
- **Security Features**:
  - Builds on `python:3.11-slim`.
  - Automatically installs user dependencies if `requirements.txt` is present.
  - Creates and switches to non-root user `faasuser` (`uid: 10001`).
  - Embeds native container healthcheck and exposes port `8080`.

---

### 5.8 Automated Backend Tests (`backend/tests/`)

#### 27. [`backend/tests/test_auth.py`](file:///d:/ACC%20Mini%20Project/backend/tests/test_auth.py)
- **Purpose**: Tests user registration, password verification, login, JWT generation, and protected `/me` profile retrieval.

#### 28. [`backend/tests/test_functions.py`](file:///d:/ACC%20Mini%20Project/backend/tests/test_functions.py)
- **Purpose**: Tests function creation, database persistence, listing user functions, and retrieving metadata.

#### 29. [`backend/tests/test_invocation.py`](file:///d:/ACC%20Mini%20Project/backend/tests/test_invocation.py)
- **Purpose**: End-to-end test executing a function, asserting output calculation (`result == 42`), verifying latency fields, and checking Prometheus metric emission.

---

### 5.9 Web Management Dashboard (`frontend/`)

#### 30. [`frontend/src/App.tsx`](file:///d:/ACC%20Mini%20Project/frontend/src/App.tsx)
- **Purpose**: Single-page application implementing the developer dashboard.
- **Components & Features**:
  - **Header Bar**: Live indicators for Kubernetes cluster status, Docker daemon, and scale-to-zero reaper.
  - **KPI Cards**: Real-time counters for Total Functions, Active Pods, Total Invocations, and Avg Warm/Cold Latencies.
  - **Tab 1: Function Catalog**: Cards displaying function name, runtime, status badge (`READY`, `RUNNING`, `SCALED_TO_ZERO`, `BUILDING`), active replica count, memory/CPU limits, and quick-invoke/delete actions.
  - **Tab 2: Function Studio**: In-browser code editor with starter templates (Hello World, Fibonacci Benchmark, JSON Transformer), memory & timeout sliders, and instant deployment.
  - **Tab 3: Invocation Console**: Interactive test client with custom JSON input editor and a 3-way latency visualizer (Cold Start ms vs. Execution ms vs. Total ms).
  - **Tab 4: Invocation Logs**: Execution history table with cold/warm indicators, timestamps, request IDs, and status codes.
  - **Tab 5: Cluster & Metrics**: Architecture overview, scale-to-zero explanation, and direct links to the Prometheus metric stream.

#### 31. [`frontend/src/main.tsx`](file:///d:/ACC%20Mini%20Project/frontend/src/main.tsx)
- **Purpose**: React 18 DOM root rendering `<App />`.

#### 32. [`frontend/src/index.css`](file:///d:/ACC%20Mini%20Project/frontend/src/index.css)
- **Purpose**: Tailwind CSS styling and theme configuration.

#### 33. [`frontend/vite.config.ts`](file:///d:/ACC%20Mini%20Project/frontend/vite.config.ts)
- **Purpose**: Vite build tool configuration with React and Tailwind plugins, including development reverse proxy forwarding `/api` requests to `http://localhost:8000`.

#### 34. [`frontend/package.json`](file:///d:/ACC%20Mini%20Project/frontend/package.json)
- **Purpose**: Defines dependencies (`react`, `react-dom`, `axios`, `lucide-react`, `tailwindcss`, `@tailwindcss/vite`).

---

### 5.10 Kubernetes Manifests (`k8s/`)

#### 35. [`k8s/namespace.yaml`](file:///d:/ACC%20Mini%20Project/k8s/namespace.yaml)
- **Purpose**: Defines isolated namespaces: `faas-fn` (for user function pods) and `faas-system` (for platform controllers).

#### 36. [`k8s/rbac.yaml`](file:///d:/ACC%20Mini%20Project/k8s/rbac.yaml)
- **Purpose**: Kubernetes ServiceAccount, ClusterRole, and ClusterRoleBinding granting the FaaS controller permissions to create, update, scale, and delete Pods, Deployments, and Services.

#### 37. [`k8s/registry.yaml`](file:///d:/ACC%20Mini%20Project/k8s/registry.yaml)
- **Purpose**: In-cluster Deployment and NodePort Service for the private Docker Registry.

---

### 5.11 Scientific Performance Benchmarks (`benchmarks/`)

#### 38. [`benchmarks/cold_start_test.py`](file:///d:/ACC%20Mini%20Project/benchmarks/cold_start_test.py)
- **Purpose**: Automates **Experiment 1 (Cold vs. Warm Start Latency)**.
- **Methodology**:
  1. Registers a benchmark function (CPU-intensive Fibonacci calculation).
  2. Executes an initial invocation on a scaled-to-zero function to capture cold-start provisioning latency.
  3. Executes 10 consecutive warm invocations against the warm container.
  4. Computes Mean, Median (p50), Min, Max, and speedup ratio (e.g. 50x-100x faster when warm).

#### 39. [`benchmarks/concurrency_test.py`](file:///d:/ACC%20Mini%20Project/benchmarks/concurrency_test.py)
- **Purpose**: Automates **Experiment 2 (Concurrent Load & Throughput)**.
- **Methodology**:
  1. Utilizes `asyncio` and `httpx` to generate simultaneous bursts of 1, 10, 50, and 100 concurrent requests.
  2. Measures throughput (Requests per Second / RPS), error rates, average latency, and 95th percentile latency (p95).

---

## 6. How to Run & Verify the Complete Platform

### 1. Enable Kubernetes on Docker Desktop
1. Open Docker Desktop $\rightarrow$ Click **Settings (Gear icon)** $\rightarrow$ **Kubernetes**.
2. Check **Enable Kubernetes** $\rightarrow$ Click **Apply & restart**.
3. Verify cluster connectivity:
   ```bash
   kubectl get nodes
   ```

### 2. Launch Local Database & Docker Registry
```bash
docker compose up -d
```

### 3. Launch Backend API & FaaS Controller
```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
- Interactive Swagger API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Prometheus Metrics Exporter: [http://localhost:8000/api/v1/metrics](http://localhost:8000/api/v1/metrics)

### 4. Launch React Web Dashboard
```bash
cd frontend
npm install
npm run dev
```
- Open [http://localhost:5173](http://localhost:5173) in your browser.

### 5. Run Automated Tests & Benchmarks
```bash
# Run backend pytest suite
python -m pytest backend/tests -v

# Run Experiment 1 (Cold vs Warm start benchmark)
python benchmarks/cold_start_test.py

# Run Experiment 2 (Concurrency load test)
python benchmarks/concurrency_test.py
```

---

## 7. Summary of Engineering Achievements

1. **True Platform Architecture**: Developed an actual FaaS platform layer (lifecycle manager, builder, scale-to-zero reaper, and telemetry) rather than simple static deployment scripts.
2. **Container Security**: Enforced unprivileged non-root users (`uid: 10001`), dropped Linux capabilities, and strict CPU/Memory resource quotas.
3. **Scale-to-Zero & Cold-Start Telemetry**: Solved idle resource consumption while providing millisecond-accurate measurement of container provisioning overhead.
4. **Full-Stack Developer Experience**: Complete end-to-end user workflow from browser-based function coding to instantaneous invocation and Prometheus observability.
