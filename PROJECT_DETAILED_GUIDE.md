# Kubernetes-Based Docker Serverless Platform

## Detailed Project Explanation and Real-World Walkthrough

## 1. What This Project Is

This project is a self-hosted **Function-as-a-Service (FaaS)** platform.

It allows a developer to:

1. Create an account.
2. Write a small function such as `handler(event)`.
3. Register that function through a web dashboard or REST API.
4. Package the function into a Docker image automatically.
5. Tag the image for the configured Docker registry and, when configured for a
   non-local registry, push it there.
6. Deploy the image as a Kubernetes workload.
7. Invoke the function with JSON data over HTTP.
8. Automatically scale the function up when traffic increases.
9. Scale the function down to zero when it has been idle.
10. View invocation results, logs, latency, replica information, and metrics.

The developer does not need to create a Dockerfile, write Kubernetes YAML for every
function, manually create a Service, or manage Pods directly. The platform performs
those tasks from the function definition and the selected configuration.

The project is conceptually similar to a small private version of:

- AWS Lambda
- Google Cloud Functions
- Azure Functions
- OpenFaaS

It is designed for learning and demonstration, but it contains the major building
blocks required by a real serverless execution platform: an API gateway, authentication,
build automation, container packaging, orchestration, routing, autoscaling, observability,
and a management dashboard.

---

## 2. The Real-World Problem It Solves

Imagine an online shopping company. Every time a customer places an order, the company
needs to validate the order:

```text
Input:
{
  "customer_id": "C1001",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "price": 499}
  ],
  "coupon": "WELCOME10"
}
```

The validation logic might be:

- Check that the cart is not empty.
- Check that quantities are positive.
- Calculate the subtotal.
- Apply a coupon.
- Reject orders above a configured limit.
- Return the final amount and validation status.

A traditional approach would require a continuously running application server. That
server would consume CPU and memory even when no customers are placing orders.

With this project, the company can register the logic as a function:

```python
def handler(event):
    items = event.get("items", [])

    if not items:
        return {"valid": False, "reason": "Cart is empty"}

    subtotal = sum(
        item["price"] * item["quantity"]
        for item in items
    )

    discount = 0.10 if event.get("coupon") == "WELCOME10" else 0
    total = round(subtotal * (1 - discount), 2)

    return {
        "valid": True,
        "customer_id": event.get("customer_id"),
        "subtotal": subtotal,
        "discount": round(subtotal * discount, 2),
        "total": total
    }
```

The platform keeps no function Pod running while the function is unused. When an order
arrives, it starts the function workload, sends the request to it, returns the result,
and later scales it down again if traffic stops.

This is the main serverless idea implemented by the project:

> Developers submit code and data. The platform manages packaging, infrastructure,
> execution, scaling, and telemetry.

---

## 3. High-Level Architecture

```text
                         Developer / Browser
                                |
                                | HTTP
                                v
                  +-----------------------------+
                  | React + Vite Dashboard      |
                  | Login, create, invoke, logs  |
                  +--------------+--------------+
                                 |
                                 | REST API + JWT/API key
                                 v
                  +-----------------------------+
                  | FastAPI Backend              |
                  | Auth, functions, invocation  |
                  | logs, metrics, cluster APIs  |
                  +---+------------+----------+--+
                      |            |          |
                      |            |          |
                      v            v          v
              +-----------+  +-----------+  +----------------+
              | Database  |  | Controller|  | Prometheus     |
              | SQLAlchemy|  | Reaper +  |  | counters and   |
              | PostgreSQL |  | autoscaler|  | histograms     |
              | or SQLite |  +-----+-----+  +----------------+
              +-----------+        |
                                   |
                      +------------+-------------+
                      |                          |
                      v                          v
               +-------------+             +-------------+
               | Docker SDK  |             | Kubernetes |
               | Image build |             | Deployments|
               +------+------+             | Services   |
                      |                    | Pods       |
                      v                    +------+------+ 
               +-------------+                    |
               | Registry    |                    |
               | localhost:  | <------------------+
               | 5000        |       image pulled by Pod
               +-------------+
                                                    |
                                                    v
                                      +-------------------------+
                                      | Python 3.11 Function Pod |
                                      | server.py + handler.py   |
                                      | HTTP /healthz, /execute  |
                                      +-------------------------+
```

### Main components

| Component | Technology | Responsibility |
|---|---|---|
| Web dashboard | React, TypeScript, Vite, Tailwind CSS | User interface for managing and invoking functions |
| API server | FastAPI, Uvicorn | REST API, request validation, authentication, orchestration workflow |
| Persistence | SQLAlchemy with PostgreSQL or SQLite fallback | Users, functions, versions, API keys, and invocation logs |
| Image builder | Docker SDK for Python | Creates a container image for each function version |
| Image registry | Docker Registry v2 | Stores function images when the configured registry is remote or otherwise push-enabled |
| Orchestrator | Kubernetes Python client | Creates Deployments and ClusterIP Services and changes replica counts |
| Runtime | Python 3.11 and a custom HTTP server | Loads and executes user code inside a function container |
| Controller | Custom asynchronous Python service | Autoscaling and scale-to-zero idle reaping |
| Metrics | `prometheus-client` | Invocation, cold-start, latency, and replica metrics |
| Tests and benchmarks | Pytest and benchmark scripts | Functional tests and performance experiments |

---

## 4. Repository Structure

```text
ACC-Mini-Project/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py          Authentication endpoints
│   │   │   ├── cluster.py       Cluster status endpoints
│   │   │   ├── functions.py     Create/list/update/delete functions
│   │   │   ├── invoke.py        Function invocation endpoints
│   │   │   ├── keys.py          Function-scoped API keys
│   │   │   ├── logs.py          Invocation history and statistics
│   │   │   └── metrics.py       Prometheus metrics endpoint
│   │   ├── core/
│   │   │   ├── config.py        Environment-backed settings
│   │   │   ├── db.py            SQLAlchemy engine and sessions
│   │   │   ├── security.py      Password hashing and JWT handling
│   │   │   └── api_keys.py      API-key hashing and rate limiting
│   │   ├── models/
│   │   │   ├── user.py          User table
│   │   │   ├── function.py      Function and version tables
│   │   │   ├── invocation.py    Invocation log table
│   │   │   └── api_key.py       API-key table
│   │   ├── schemas/             Pydantic request and response models
│   │   ├── services/
│   │   │   ├── builder.py       Docker image creation
│   │   │   ├── controller.py    Reaper and autoscaler loops
│   │   │   ├── k8s_client.py    Kubernetes API integration
│   │   │   ├── router.py        Version routing and invocation execution
│   │   │   ├── autoscaler.py    Desired replica calculation
│   │   │   └── naming.py        Safe Kubernetes resource names
│   │   └── main.py              FastAPI application entry point
│   ├── runtimes/python311/
│   │   ├── Dockerfile.template  Runtime image definition
│   │   └── server.py            Container-side function HTTP server
│   └── tests/                   Backend tests
├── frontend/
│   ├── src/App.tsx              Main dashboard
│   ├── src/ApiAccessPanel.tsx   API-key and endpoint information
│   ├── src/index.css            Dashboard styling
│   └── package.json             Frontend dependencies and scripts
├── k8s/
│   ├── namespace.yaml           FaaS namespaces
│   ├── rbac.yaml                Kubernetes permissions
│   ├── networkpolicy-egress.yaml
│   ├── networkpolicy-ingress.yaml
│   └── registry.yaml             Registry deployment configuration
├── benchmarks/
│   ├── cold_start_test.py       Cold versus warm latency
│   ├── concurrency_test.py      Concurrent throughput
│   └── scaling_test.py          Replica and autoscaling experiments
├── docker-compose.yml            Local PostgreSQL and registry
├── pytest.ini                    Pytest configuration
└── README.md                     Original quick-start documentation
```

---

## 5. Authentication and Tenant Isolation

### Registration

The user registers through:

```text
POST /api/v1/auth/register
```

The backend:

1. Validates the submitted username, email, and password.
2. Hashes the password with bcrypt.
3. Stores the user in the database.
4. Returns a signed JWT access token.

The password itself is not stored as plain text.

### Login

The dashboard submits username and password to:

```text
POST /api/v1/auth/login
```

The backend verifies the password and returns a JWT. The frontend stores the token in
browser local storage and sends it as:

```text
Authorization: Bearer <jwt-token>
```

### Ownership isolation

Function names are unique per owner rather than globally. Therefore:

```text
Alice -> order-validator
Bob   -> order-validator
```

are two separate functions.

The backend always resolves an owner-facing function by:

```text
(owner_id, function_name)
```

This prevents one user from reading or invoking another user's function merely by
guessing its name.

---

## 6. Creating a Function

The dashboard's Create Function form sends code and configuration to:

```text
POST /api/v1/functions/
```

A typical request contains:

```json
{
  "name": "order-validator",
  "runtime": "python311",
  "description": "Validates an ecommerce order",
  "code": "def handler(event): ...",
  "requirements": "",
  "memory_limit": "256Mi",
  "cpu_limit": "500m",
  "timeout_seconds": 10,
  "min_replicas": 0,
  "max_replicas": 5,
  "target_concurrency": 5
}
```

### What happens in the database

The backend immediately creates:

1. A `Function` record.
2. A `FunctionVersion` record for `v1`.

The function initially has a status such as `CREATING`. The version is not considered
active until its image has been built and the deployment has become ready.

This distinction is important. A function should not be routed to while its image is
still being built or while its Pod is failing its readiness check.

---

## 7. Image Build Process

The build task runs after the function request has been accepted.

The `BuilderService` creates a temporary build directory containing:

```text
handler.py          User-submitted code
requirements.txt    Optional Python dependencies
server.py           Standard platform runtime
Dockerfile          Copied from the runtime template
```

The image is tagged using the registry, username, function name, and version:

```text
localhost:5000/<username>/<function-name>:v1
```

The Docker SDK then builds the image. A later version might use:

```text
localhost:5000/<username>/order-validator:v2
```

Each version has its own image tag. This makes rollback and version-pinned invocation
possible.

The builder pushes the image only when the configured registry is not a `localhost`
registry. With the default local configuration, the image is tagged and remains in the
local Docker daemon. This works with a local Docker Desktop Kubernetes cluster because
the cluster can use the locally available image with `IfNotPresent`; a separately
configured remote registry receives an explicit image push.

### Why build a separate image?

The function's dependencies and source code must not be mixed into the backend process.
The image gives every version a repeatable runtime containing:

- A known Python version.
- The exact submitted source.
- The requested Python packages.
- The standard platform runner.
- The function timeout setting.

---

## 8. Kubernetes Deployment

After the image is built, the Kubernetes service creates:

1. A Deployment.
2. A ClusterIP Service.
3. One or more Pods controlled by that Deployment.

The generated Deployment includes:

- The function image.
- CPU and memory requests/limits.
- A readiness probe against `/healthz`.
- A non-root security context.
- All Linux capabilities dropped.
- Privilege escalation disabled.
- A read-only root filesystem.
- A writable `/tmp` volume limited to 64 MiB.
- No automatically mounted Kubernetes service-account token.
- Disabled service links.
- A RuntimeDefault seccomp profile.

For the order example, Kubernetes may receive a resource conceptually equivalent to:

```text
Deployment: fn-<owner>-order-validator-v1
Service:    fn-<owner>-order-validator-v1
Container:  localhost:5000/shop/order-validator:v1
Port:       8080
Replicas:   0 or 1 initially, depending on configuration
```

The platform waits for a Ready Pod before marking the version active.

### Why use a Deployment?

A Deployment gives the platform:

- Replica management.
- Pod replacement if a Pod crashes.
- Rolling update behavior.
- A stable desired-state object that can be scaled.

### Why use a ClusterIP Service?

The Service provides a stable internal endpoint even when individual Pods are replaced.
The backend can therefore route to the function workload without depending on a
particular Pod IP.

---

## 9. The Python 3.11 Runtime

Every generated function image includes the standard `server.py` runtime.

The runtime:

1. Imports the `handler` module.
2. Finds `handler(event)` or `main(event)`.
3. Starts an HTTP server on port `8080`.
4. Returns readiness from `/healthz`.
5. Accepts execution requests at `/execute`.
6. Parses the incoming JSON.
7. Calls the user's handler.
8. Returns the result as JSON.

For the e-commerce example:

```text
POST /execute
Content-Type: application/json

{
  "customer_id": "C1001",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "price": 499}
  ],
  "coupon": "WELCOME10"
}
```

The runtime returns a response containing:

```json
{
  "statusCode": 200,
  "result": {
    "valid": true,
    "customer_id": "C1001",
    "subtotal": 998,
    "discount": 99.8,
    "total": 898.2
  },
  "execution_time_ms": 1.4
}
```

The runtime also handles:

- Empty request bodies.
- Invalid JSON.
- Missing handler functions.
- Handler exceptions.
- Execution timeouts.

An execution that exceeds the configured timeout returns an HTTP 504-style result.

---

## 10. Invocation Flow

The owner can invoke the newest ready version with:

```text
POST /api/v1/invoke/order-validator
```

A specific version can be selected with:

```text
POST /api/v1/invoke/order-validator/v1
```

There is also a stable public-id route. The public ID makes the endpoint stable and
does not make it anonymous; the caller must still provide the owner's JWT or a
function-scoped API key:

```text
POST /api/v1/f/<public_id>
POST /api/v1/f/<public_id>/<version>
```

### Detailed request flow

For an order request, the flow is:

```text
1. Browser or checkout service sends a JSON request.
2. FastAPI authenticates the JWT or function API key.
3. The function is resolved for the authenticated owner.
4. The requested version is resolved.
5. Only an active, ready version is routable.
6. The router checks whether the version is warm.
7. If cold, the controller scales its Deployment up.
8. The backend waits for a Ready Pod.
9. The request is sent to the runtime's /execute endpoint.
10. The runtime calls handler(event).
11. The result travels back through the router and API.
12. Metrics are updated.
13. An invocation log is queued and written to the database.
14. The response is returned to the caller.
```

### Latest-version behavior

When no version is supplied, the router selects the newest version whose
`is_active` flag is true. A newly created version that is still building is not selected.

This avoids sending production traffic to a partially deployed version.

---

## 11. Cold Starts and Warm Invocations

### Cold start

A function is cold when its Deployment has been scaled to zero or has not yet been
started for the requested version.

For a cold order-validator invocation:

```text
No ready Pod
      |
      v
Scale Deployment from 0 to 1
      |
      v
Wait for image pull and readiness probe
      |
      v
Send request to the ready runtime
```

The platform records:

- Whether the call was a cold start.
- Cold-start duration.
- Function execution duration.
- Total duration.

### Warm invocation

After a function has a ready Pod, another request can be handled without starting a new
Pod:

```text
Ready Pod
   |
   v
Send /execute request immediately
```

Warm invocations normally have lower latency because image pulling, container startup,
module loading, and readiness checks have already happened.

The dashboard displays the difference between cold-start and warm execution behavior.

---

## 12. Autoscaling

Each function has:

| Setting | Meaning |
|---|---|
| `min_replicas` | Lowest allowed replica count |
| `max_replicas` | Highest allowed replica count, capped by the platform |
| `target_concurrency` | Approximate number of in-flight requests one Pod should handle |

The project controller periodically measures in-flight work. Conceptually, its desired
replica calculation is:

```text
desired_replicas = ceil(in_flight_requests / target_concurrency)
```

The result is clamped to the configured range:

```text
max(min_replicas, calculated_replicas)
through
max_replicas
```

Example:

```text
in_flight_requests = 18
target_concurrency = 5
calculated replicas = ceil(18 / 5) = 4
```

If the function is configured with `min_replicas=1` and `max_replicas=5`, the desired
count is 4.

### Fixed replica mode

Setting:

```text
min_replicas = max_replicas = 3
```

keeps the function at three replicas. This is useful for benchmark experiments or
latency-sensitive production-like workloads.

### Scale-down stabilization

The autoscaler does not immediately remove replicas after a short lull. It uses a
stabilization period so that a brief traffic dip does not cause repeated scale-up and
scale-down cycles.

This reduces replica flapping.

---

## 13. Scale-to-Zero Reaper

The `FaasController` starts two background loops when FastAPI starts:

1. The autoscaler loop.
2. The scale-to-zero reaper loop.

The reaper periodically checks functions with active replicas. If:

```text
current time - last invocation time > idle timeout
```

and `min_replicas` is zero, the controller:

1. Stops tracking the function in the autoscaler.
2. Scales the function's Deployments to zero.
3. Marks the function as cold.
4. Sets the database replica count to zero.
5. Sets the status to `SCALED_TO_ZERO`.

The next invocation starts the cold-start process again.

This is how the platform saves resources for functions that are used only occasionally.

---

## 14. API Keys and Public Invocation

JWTs are convenient for the dashboard and owner management operations. External systems
such as a checkout service often need a narrower credential, so the project also
supports function-scoped API keys.

An API key can be:

- Limited to one function.
- Pinned to a particular version.
- Revoked.
- Rate limited.

The caller can send it through:

```text
X-API-Key: <function-api-key>
```

or the supported bearer form.

For the order example, the checkout service can invoke only `order-validator` without
receiving permission to list or modify the developer's other functions.

The invocation layer also prevents an API key for one function from being used against
another function. It returns a not-found response rather than exposing whether another
function exists.

---

## 15. Database Design

The main entities are:

### User

Stores:

- Username.
- Email.
- Password hash.
- User-owned functions.

### Function

Stores:

- Name and stable public ID.
- Owner.
- Runtime.
- Description.
- Current status.
- Resource limits.
- Timeout.
- Replica settings.
- Last invocation time.

### FunctionVersion

Stores:

- Function relationship.
- Version tag such as `v1` or `v2`.
- Submitted code.
- Python requirements.
- Docker image tag.
- Active/ready state.

### InvocationLog

Stores:

- Request ID.
- Function and version.
- Timestamp.
- Input and output payloads.
- Status code.
- Error information.
- Cold-start flag.
- Cold-start duration.
- Execution duration.
- Total duration.
- Actual execution location.

### ApiKey

Stores a hashed function-scoped key and its policy, including optional version pinning
and revocation state.

### Database selection

The configuration supports:

- PostgreSQL for the Docker-based local stack or a deployed environment.
- SQLite fallback for standalone development and tests.

The repository's `docker-compose.yml` provides PostgreSQL and a local Docker Registry.

---

## 16. Observability and Metrics

The backend exposes Prometheus-compatible metrics through:

```text
GET /api/v1/metrics
```

The implementation tracks metrics including:

- Total invocation count.
- Invocation status.
- Total invocation duration.
- Cold-start count.
- Active replicas.

The database logs provide more detailed per-request information than aggregate metrics.

For the order-validator example, an operator could answer:

- How many orders were processed?
- How many calls failed?
- How often did cold starts happen?
- What is the average execution time?
- How long did startup add to the request?
- How many replicas are currently active?
- When was the function last used?

The dashboard also computes summary values such as:

- Total functions.
- Active replicas.
- Number of scaled-to-zero functions.
- Total invocations.
- Cold-start count.
- Warm invocation count.
- Cold-start ratio.
- Average execution duration.
- Average cold-start duration.

---

## 17. Frontend Dashboard

The React dashboard provides a visual interface over the backend API.

### Authentication view

Users can register or log in. The dashboard stores the JWT locally and includes it in
future API requests.

### Function catalog

The catalog shows:

- Function names.
- Status.
- Runtime.
- Resource limits.
- Active replicas.
- Scaling configuration.
- Last invocation time.

### Create function view

The form lets the user enter:

- Name.
- Description.
- Python runtime.
- Function code.
- Dependencies.
- Memory.
- CPU.
- Timeout.
- Minimum replicas.
- Maximum replicas.
- Target concurrency.

The dashboard includes example templates such as:

- Hello world.
- Fibonacci computation.
- JSON transformation.

### Invocation view

The user selects a function, supplies JSON, and invokes it. The UI shows:

- The returned result.
- Status code.
- Cold/warm information.
- Execution timing.
- Error details if the call fails.

### Logs and statistics view

The dashboard loads invocation history and aggregate statistics from the backend.

### Cluster view

The UI can display cluster-related information returned by the cluster API, which helps
show whether Kubernetes is available and what the platform currently sees.

### API access panel

The dashboard provides information about stable public IDs and function API access,
which is useful when integrating an external checkout service or benchmark client.

---

## 18. Local Development and Fallback Modes

The complete production-style path uses:

```text
Docker -> Registry -> Kubernetes -> Function Pod
```

However, the project also contains local fallback behavior.

### Docker unavailable

The image builder can report a mocked build result when Docker is unavailable. This is
useful for tests or inspecting the API flow, but it does not create a real runnable
function image.

### Kubernetes unavailable

The Kubernetes service detects whether it can load a cluster configuration. If it
cannot connect, it runs in standalone/fallback mode for supported development flows.

### Local sandbox

The configuration includes:

```text
ALLOW_LOCAL_SANDBOX=true
```

When enabled, the backend can execute user code with Python `exec()` in the API process.
This is intended only for local development and tests. It is not a security boundary
and must not be enabled for an untrusted production workload.

The safer production path is execution in a restricted Kubernetes Pod with the
configured security controls.

---

## 19. Complete Order-Validation Example

### Step A: Developer registers

The developer creates an account through the dashboard:

```text
username: shop-platform
email: ops@example.com
```

The backend creates a user and returns a JWT.

### Step B: Developer creates the function

The developer enters:

```text
Name: order-validator
Runtime: python311
Memory: 256Mi
CPU: 500m
Timeout: 10 seconds
Minimum replicas: 0
Maximum replicas: 5
Target concurrency: 5
```

The function starts in `CREATING` and then changes to `BUILDING`.

### Step C: The image is built

The builder creates:

```text
handler.py
requirements.txt
server.py
Dockerfile
```

Then it builds:

```text
localhost:5000/shop-platform/order-validator:v1
```

### Step D: Kubernetes is configured

The backend creates a Deployment and ClusterIP Service. The build/deploy task starts
the Deployment with at least one replica so that the version can become ready, even
when `min_replicas` is zero. After the configured idle timeout, the controller's
scale-to-zero reaper can reduce it to zero. A later request then causes a cold start.

### Step E: Checkout service receives an order

The checkout service sends:

```http
POST /api/v1/f/<public_id>
X-API-Key: <order-validator-key>
Content-Type: application/json
```

with:

```json
{
  "customer_id": "C1001",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "price": 499}
  ],
  "coupon": "WELCOME10"
}
```

### Step F: The first call is cold

The router observes that `order-validator:v1` is cold, scales it from zero to one,
waits for `/healthz`, and sends the order to `/execute`.

The response contains the calculated total. The log records the additional cold-start
time.

### Step G: More orders arrive

Five simultaneous requests can be handled by one Pod according to the target
concurrency setting. If 18 requests are in flight, the autoscaler can request four
replicas, subject to the configured maximum.

### Step H: The workload becomes idle

After the configured idle period with no traffic, the controller scales the function
back to zero. The next order experiences another cold start, while the platform avoids
using cluster resources during inactivity.

### Step I: Version 2 is released

The developer changes the coupon logic and submits an update. The platform builds:

```text
localhost:5000/shop-platform/order-validator:v2
```

The old version can remain available while v2 builds. Once v2 has a ready Pod, it
becomes the newest active version for unpinned calls.

An API key pinned to `v1` continues using v1 until deliberately changed.

---

## 20. Security and Isolation Controls

The project uses multiple layers of protection:

### API layer

- JWT authentication.
- Owner-based function lookup.
- Function-scoped API keys.
- API-key revocation.
- API-key rate limiting.
- Payload-size checks.
- Version pinning.

### Container and Kubernetes layer

- Non-root execution.
- Fixed non-root user ID.
- Privilege escalation disabled.
- Linux capabilities dropped.
- Read-only root filesystem.
- Limited writable `/tmp`.
- No service-account token mounted into function Pods.
- Disabled automatic service links.
- RuntimeDefault seccomp profile.
- CPU and memory limits.
- Readiness probes.

### Important limitation

`ALLOW_LOCAL_SANDBOX=true` executes submitted code inside the API process. This is
intentionally marked unsafe. It should only be used on a trusted local machine for
development or tests.

---

## 21. Error and Status Lifecycle

A function can move through statuses such as:

```text
CREATING
   |
   v
BUILDING
   |
   +--> ERROR
   |
   v
READY
   |
   v
RUNNING
   |
   v
IDLE
   |
   v
SCALED_TO_ZERO
```

Examples:

- `CREATING`: database records exist, but build work has not completed.
- `BUILDING`: Docker image creation or deployment is in progress.
- `READY`: at least one version is deployed and routable.
- `RUNNING`: the function has active invocation activity.
- `IDLE`: it remains available but has not recently received traffic.
- `SCALED_TO_ZERO`: no replicas are running because of inactivity.
- `ERROR`: the build or deployment failed and no ready version is available.

If a new version fails while an older version is still ready, the older version can
continue serving traffic. This is an important availability behavior.

---

## 22. Typical Development Commands

### Create and activate the project virtual environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### Start PostgreSQL and the local registry

```powershell
docker compose up -d
```

### Start the backend

```powershell
$env:ALLOW_LOCAL_SANDBOX="true"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app `
  --host 0.0.0.0 --port 8000 --reload
```

For Kubernetes-backed execution, use the appropriate Kubernetes configuration and
avoid enabling the local sandbox.

### Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

### Useful URLs

```text
Frontend:    http://127.0.0.1:5173/
API docs:    http://127.0.0.1:8000/docs
Metrics:     http://127.0.0.1:8000/api/v1/metrics
```

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -v
```

---

## 23. Performance Experiments

The benchmark scripts evaluate the platform from different angles.

### Cold-start experiment

Measures the difference between:

- The first request after scale-to-zero.
- Later warm requests.

This demonstrates the startup overhead created by image/container readiness.

### Concurrency experiment

Sends concurrent requests at different worker counts and measures:

- Throughput.
- Average latency.
- Percentile latency.
- Error behavior.

### Scaling experiment

Uses fixed replica configurations and autoscaling behavior to study how throughput and
latency change as the number of Pods changes.

The function runtime returns execution timing, while the backend records total and
cold-start timing, allowing the experiment to separate:

```text
platform startup cost
from
actual user-code execution cost
```

---

## 24. What Happens in One Sentence

The complete platform workflow is:

> A developer submits Python code through React, FastAPI stores and authenticates it,
> Docker packages it into a versioned image, the registry stores the image, Kubernetes
> runs it in a constrained Pod, the router invokes it on demand, the controller scales
> it according to traffic, and the database plus Prometheus record what happened.

---

## 25. Final Summary

This project is not just a Python function runner. It is a complete educational
implementation of the infrastructure around serverless functions.

Its most important ideas are:

1. **Code is separated from infrastructure.** Developers submit handlers rather than
   manually managing containers.
2. **Every version is packaged consistently.** Docker creates repeatable runtime images.
3. **Kubernetes manages availability.** Deployments, Services, readiness probes, and
   replicas provide a real orchestration layer.
4. **Routing understands readiness.** Building or failed versions are not invoked.
5. **Scale-to-zero reduces idle cost.** Unused functions do not need permanently running
   Pods.
6. **Autoscaling responds to demand.** Replica counts follow in-flight concurrency.
7. **Authentication provides ownership isolation.** Users can manage only their own
   functions.
8. **API keys support integrations.** External systems can invoke one function with
   restricted credentials.
9. **Observability makes behavior measurable.** Logs and metrics expose errors,
   cold-start cost, execution time, and replica activity.
10. **The dashboard makes the platform usable.** The full lifecycle can be demonstrated
    without manually calling every API endpoint.

For an e-commerce company, the result is a platform where order validation, fraud
checks, invoice generation, image processing, notification dispatch, and similar
event-driven tasks can be deployed as independently scalable functions.
