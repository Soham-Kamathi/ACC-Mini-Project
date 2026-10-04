# Project Status

**Project:** Kubernetes-Based Docker Serverless (FaaS) Function Execution Platform
**Last updated:** 2026-10-04
**Test suite:** 29 backend tests, all passing (`.venv\Scripts\python.exe -m pytest backend/tests -q`). The tests stub Docker and Kubernetes, so they run anywhere.

This file records what has been built, what was changed and fixed in the latest hardening pass, what has and has not been verified, and what is still open. `tasks.md` is the older checklist; where the two disagree, this file is newer.

---

## 1. What the platform does

1. A user registers and logs in (JWT) and creates a function: Python source, an optional `requirements.txt`, resource limits and a timeout.
2. The backend builds a Docker image, deploys it to Kubernetes (Deployment and ClusterIP Service in namespace `faas-fn`) and marks the version ready once a Pod is actually serving.
3. The function can be called three ways:
   - `POST /api/v1/invoke/{name}[/{version}]` with the owner's JWT or an API key
   - `POST /api/v1/f/{public_id}[/{version}]` with an API key or the owner's JWT (the public endpoint)
4. A background reaper scales idle functions to zero replicas; the next call cold-starts the Pod and reports the cold-start time separately from execution time.
5. Metrics are exported at `/api/v1/metrics` (Prometheus) and shown in the React dashboard together with logs and cluster health.

Where data lives: users, functions, version source code, API key hashes and invocation logs are in the SQLite file `faas_metadata.db`. Images are in the local Docker image store. Deployments and Pods are in Kubernetes. Warm/cold state, short caches, the unflushed log queue and Prometheus counters are in memory and reset on restart.

---

## 2. Completed work

### 2.1 Core platform (earlier work)
- [x] FastAPI REST API, JWT auth with bcrypt, per-user function ownership
- [x] Function CRUD, immutable versions, status state machine
- [x] Dynamic image builder (Dockerfile assembly, Docker SDK build)
- [x] Kubernetes orchestration with resource limits and readiness probes
- [x] Scale-to-zero controller (reaper loop) and on-demand cold start with timing telemetry
- [x] Prometheus exporter and dashboard KPI endpoint (`/stats`)
- [x] React + Vite + Tailwind dashboard (catalog, studio, invoke console, logs, cluster health)
- [x] Benchmarks: Experiment 1 (cold vs warm) and Experiment 2 (concurrency)

### 2.2 Security and correctness pass (this round)

**In-process code execution removed**
- Before: when Kubernetes failed or returned a 5xx, the router ran user code with `exec()` inside the API process. That gave any registered user code execution on the host and could hide real failures behind a "successful" result.
- Now: the fallback exists only when `ALLOW_LOCAL_SANDBOX=true` (default `false`; unsafe, for local development without a cluster). Otherwise a function with no deployment returns status 503 with `executed_on="none"`.
- Every invoke response and every log row records `executed_on` (`k8s`, `sandbox` or `none`). The benchmarks abort if any call did not run on Kubernetes.
- The fallback only triggers on 502/503 or a transport error, never on a 500/504 produced by the function itself.

**Versioned invocation is real**
- Before: every update replaced the single Deployment, so `/invoke/{name}/v1` ran the newest code.
- Now: one Deployment and Service per version, named `fn-<owner_id>-<name>-<version>`, all labelled `faas-function=<owner_id>-<name>`.
- A version becomes routable only after its build and deploy succeed. The previous version keeps serving while a new one builds, and a failed build no longer takes down a working function.
- Version tags use max+1 (not count+1) and duplicates are rejected with 400.

**Tenant isolation**
- Invoke requires a credential. Functions are looked up by `(owner, name)`, so two users can both own `hello` without colliding in the database or in Kubernetes (the owner id is part of every resource name).
- Names must be DNS-1123 labels (1-30 characters); version tags are validated the same way.

**Per-function API keys and public endpoint**
- Each function has a stable, unguessable `public_id` and the public route `POST /api/v1/f/{public_id}`.
- Owners create, list, rotate and revoke keys (`/api/v1/functions/{name}/keys`). Up to 10 active keys per function.
- Keys look like `fk_...` and are shown once. Only a SHA-256 hash is stored, along with a short prefix, label, optional version pin, created time and last-used time.
- A key is valid for exactly one function and cannot manage functions or read logs. A key used against another function gets 404, so keys cannot probe which functions exist.
- A key can be pinned to a version (for example `v1`) so a client does not change behaviour when a new version is published.
- Accepted as `X-API-Key: fk_...` or `Authorization: Bearer fk_...`. The owner's JWT also works on both routes.
- Per-key rate limit (default 120 requests/minute, answered with 429 and `Retry-After`) and a request body cap (default 1 MiB, answered with 413). The JWT owner is not subject to the per-key limit.
- The dashboard Invoke tab has an API Access panel: endpoint, key table, create/rotate/revoke, a one-time key display, and ready-made `curl` and Python snippets.

**Network isolation**
- `k8s/networkpolicy-egress.yaml`: function Pods may resolve DNS and reach the public internet only. All private, link-local and CGNAT ranges are blocked, which covers other function Pods, cluster Services, the Kubernetes API server, the registry, the node and the cloud metadata endpoint.
- `k8s/networkpolicy-ingress.yaml`: default-deny ingress, then TCP 8080 allowed only from the `faas-system` namespace (for an in-cluster backend).
- Both manifests pass a server-side dry run against the local cluster. See section 4 for what that does and does not prove.

**Pod hardening**
- Non-root (uid 10001), all capabilities dropped, no privilege escalation, read-only root filesystem with a 64 MiB `/tmp`, seccomp `RuntimeDefault`, no service-account token mounted, no injected service environment variables.

**Bugs found by running against a real cluster**
- Invoking through the Kubernetes API proxy failed on the installed client (`kubernetes` 36.x removed the `response_type` argument). The old sandbox fallback had been masking this, which means the earlier README benchmark numbers were almost certainly not measuring Pods. Fixed by reading the raw HTTP response.
- A Pod that was still shutting down after a scale-to-zero was counted as ready, so the first call after it hit a Service with no endpoints (503). Terminating Pods are now skipped.
- The function's `timeout_seconds` was never passed to the Pod (the runtime always used 10 s). It is now set as `EXECUTION_TIMEOUT` on the Deployment.
- The runtime's timeout waited for the timed-out handler thread to finish, delaying the response. It no longer blocks. Note that a timed-out handler keeps running inside its Pod until it finishes; the CPU and memory limits bound the damage.
- The backend waited for a Pod only on cold starts, so a call right after deploy could hit a Pod that was not ready. A version is now marked ready only after a Pod reports ready.

**Tests and tooling**
- New tests: isolation between users, versioned routing (including per-version Deployment names), sandbox gating, DNS-1123 validation, the full API-key lifecycle (create, one-time display, rotate, revoke, pinning, rate limit, payload cap, cross-function and cross-user access).
- `backend/tests/conftest.py` makes every test hermetic (no Docker or Kubernetes needed). `pytest.ini` added.
- Database migration: existing databases gain the new columns (`executed_on`, `public_id`) and a unique index on startup. Verified against a copy of the real database (21 existing functions backfilled).

---

## 3. Verified end to end on the local cluster

Run against Docker Desktop Kubernetes with `ALLOW_LOCAL_SANDBOX=false`:

| Check | Result |
|---|---|
| Build, deploy, call through the public endpoint with an API key | 200, `executed_on=k8s` |
| Pod identity | uid 10001 (non-root), read-only root filesystem did not break the runtime |
| Update to v2: latest vs pinned `v1` | latest returns v2 output, pinned returns v1 output (separate Deployments) |
| Handler raises an exception | 500 with the real error message, not re-executed elsewhere |
| Handler exceeds its 3 s timeout (8 s sleep) | 504 "timed out after 3s" returned after 3.1 s by the Pod itself |
| Call after a scale-to-zero and backend restart | genuine cold start (about 1.9 s to provision), then warm calls in under 1 ms of execution |

---

## 4. Known limitations and open items

**Not yet done**
- [ ] **Re-run Experiments 1 and 2.** The numbers in the README predate these fixes and are marked as unverified. The scripts now fail loudly if any call did not run in a Pod.
- [ ] **Experiment 3 (replica scaling)** has no script, and the router only ever scales to one replica. Needs a configurable replica count or an HPA first.
- [ ] Prometheus scrape config and Grafana service/dashboard (the exporter exists; the stack does not).
- [ ] Stdout/stderr capture per invocation, shown in the dashboard.
- [ ] Environment variables / secrets for functions.
- [ ] Node.js runtime and a runtime selector in the UI.
- [ ] Dashboard: edit/update a function, choose a version in the invoke console, manual scale button.
- [ ] Rebuild action for images lost after a Docker reset (source is in the database, nothing rebuilds it).

**Things to know**
- **Network policies are not enforced on Docker Desktop.** Its built-in Kubernetes has no policy-enforcing network plugin, so the objects are accepted but have no effect locally. They need Calico, Cilium or similar. A dry run only proves the manifests are valid, not that traffic is blocked.
- **Apply the ingress policy only for an in-cluster backend.** With the backend outside the cluster (current dev setup), calls arrive through the API server proxy, whose source address depends on the network plugin, so default-deny ingress could block them. In that mode apply only the egress policy.
- Apply with: `kubectl apply -f k8s/networkpolicy-egress.yaml` (and `-f k8s/networkpolicy-ingress.yaml` for an in-cluster backend).
- The SQLite path is relative to where `uvicorn` is started. Start it from another folder and you get a new empty database. Set `DATABASE_URL` to an absolute path (or move to the Postgres container in `docker-compose.yml`, which the code does not use yet).
- Rate limiting and warm/cold state are in memory, so they are per backend process and reset on restart. After a restart the first call per version is reported as a cold start even if the Pod is still running.
- Log entries are queued in memory and written in batches; a crash can lose the last few.
- The request-size cap checks `Content-Length`; a chunked upload without that header is not capped.
- All function Pods share one namespace. Network policy is what separates them, so isolation depends on a CNI that enforces it.
- Leftover Deployments from earlier test runs (scaled to 0) may exist in `faas-fn` under the old and new naming schemes. Remove with `kubectl -n faas-fn delete deploy,svc --all` if you have no functions you want to keep there.
- `datetime.utcnow()` is deprecated and still used in several places.
- `SECRET_KEY` has a development default. Set it in the environment for anything beyond local use.

---

## 5. Recommended next steps

1. Re-run Experiments 1 and 2 against the cluster and replace the README numbers.
2. Add replica count / HPA support, then write Experiment 3 (1, 2, 5, 10 replicas).
3. Add Prometheus and Grafana to `docker-compose.yml` with a provisioned dashboard (cold-start ratio, RPS, p50/p95/p99).
4. Capture stdout/stderr per invocation and show it in the dashboard.
5. Move the database to Postgres (already in compose) and make the rate limiter and warm state shared, if the API will run as more than one process.
6. Prepare the course deliverables: architecture diagram, comparison against an always-on container baseline, and the final report.
