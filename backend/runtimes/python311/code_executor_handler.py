"""
Python Code Execution Handler for the FaaS Platform.

This is a standard handler(event) function that can be deployed as any other
FaaS function.  When invoked, it receives submitted Python source code and
standard input, executes the code in a subprocess, and returns the captured
stdout, stderr, exit code, and timing information.

Security model:
  - Code is NEVER executed with exec() inside the server process.
  - Each submission runs in a fresh subprocess with a sanitised environment.
  - Execution happens inside a hardened Kubernetes Pod (runAsNonRoot,
    readOnlyRootFilesystem, drop ALL capabilities, resource limits).
  - Temporary files are written to /tmp (the only writable mount) and cleaned
    up in a finally block.
  - stdout and stderr are size-capped to prevent memory exhaustion.

Documented limitations (see implementation plan):
  - The subprocess shares the Pod's network namespace and can make outbound
    calls unless a Kubernetes NetworkPolicy blocks egress.
  - Multiple submissions share the same Pod process space.  For stronger
    isolation, evaluate gVisor or per-submission Kubernetes Jobs.
"""

import os
import sys
import json
import uuid
import time
import shutil
import subprocess
import tempfile
import threading

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_CODE_BYTES       = 64 * 1024          # 64 KB source code limit
MAX_STDIN_BYTES      = 1 * 1024 * 1024    # 1 MB stdin limit
MAX_STDOUT_BYTES     = 1 * 1024 * 1024    # 1 MB stdout capture
MAX_STDERR_BYTES     = 256 * 1024         # 256 KB stderr capture
MIN_TIMEOUT          = 1                  # seconds
MAX_TIMEOUT          = 30                 # seconds
DEFAULT_TIMEOUT      = 5                  # seconds
MAX_CONCURRENT       = int(os.getenv("CODE_EXEC_MAX_CONCURRENT", "10"))
SUPPORTED_LANGUAGES  = {"python"}

# Base directory for execution workspaces.
# In the Docker container the only writable mount is /tmp.
# On Windows (local testing) fall back to the system temp directory.
def _pick_exec_base():
    if os.name != "nt" and os.path.isdir("/tmp") and os.access("/tmp", os.W_OK):
        return "/tmp"
    return tempfile.gettempdir()

_EXEC_BASE_DIR = _pick_exec_base()

# Python interpreter to use for subprocesses.
# In the Docker container "python3" is on the PATH.
# On Windows the executable is "python" (or the full venv path).
_PYTHON_BIN = "python3" if shutil.which("python3") else sys.executable

# Semaphore to cap concurrent subprocesses inside one Pod.
_semaphore = threading.Semaphore(MAX_CONCURRENT)

# Environment variables that must NOT leak into user subprocesses.
_SECRET_ENV_KEYS = {
    "SECRET_KEY", "DATABASE_URL", "DOCKER_REGISTRY", "DOCKER_SOCKET",
    "K8S_NAMESPACE", "K8S_IN_CLUSTER", "ALLOW_LOCAL_SANDBOX",
    "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
    "NGROK_AUTHTOKEN", "NGROK_DOMAIN",
}


def _clean_env():
    """Return a minimal environment dict safe for the user subprocess."""
    env = {}
    for key, val in os.environ.items():
        if key.upper() in _SECRET_ENV_KEYS:
            continue
        env[key] = val
    # Ensure a sane PATH so the subprocess can find python3
    if "PATH" not in env:
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    # Prevent Python from writing .pyc files (read-only filesystem)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _truncate(data: bytes, limit: int):
    """Truncate bytes and return (decoded_str, was_truncated)."""
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace"), False
    return data[:limit].decode("utf-8", errors="replace"), True


def handler(event):
    """
    FaaS handler entry point.

    Expected event keys:
      - language        : str   – must be "python" (required)
      - code            : str   – Python source code (required)
      - stdin           : str   – standard input to feed the program (optional, default "")
      - timeout_seconds : int   – execution time limit 1–30 (optional, default 5)

    Returns a dict with:
      - status           : str   – success | runtime_error | time_limit_exceeded |
                                   memory_limit_exceeded | invalid_request
      - exit_code        : int   – process exit code (None if timed out)
      - stdout           : str   – captured standard output
      - stderr           : str   – captured standard error
      - execution_time_ms: float – wall-clock execution duration
      - timed_out        : bool  – whether the execution was killed for exceeding the time limit
      - stdout_truncated : bool  – whether stdout was truncated to the size limit
      - stderr_truncated : bool  – whether stderr was truncated to the size limit
    """

    # ------------------------------------------------------------------
    # 1. Input validation
    # ------------------------------------------------------------------
    if not isinstance(event, dict):
        return _error("invalid_request", "Event must be a JSON object")

    language = event.get("language", "").strip().lower()
    code     = event.get("code", "")
    stdin    = event.get("stdin", "")
    timeout  = event.get("timeout_seconds", DEFAULT_TIMEOUT)

    if not language:
        return _error("invalid_request", "Missing required field: language")

    if language not in SUPPORTED_LANGUAGES:
        return _error("invalid_request",
                       f"Unsupported language '{language}'. Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}")

    if not code or not isinstance(code, str):
        return _error("invalid_request", "Missing or empty required field: code")

    if len(code.encode("utf-8", errors="replace")) > MAX_CODE_BYTES:
        return _error("invalid_request",
                       f"Source code exceeds maximum size of {MAX_CODE_BYTES // 1024} KB")

    if not isinstance(stdin, str):
        stdin = str(stdin)

    if len(stdin.encode("utf-8", errors="replace")) > MAX_STDIN_BYTES:
        return _error("invalid_request",
                       f"Standard input exceeds maximum size of {MAX_STDIN_BYTES // (1024 * 1024)} MB")

    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(MIN_TIMEOUT, min(MAX_TIMEOUT, timeout))

    # ------------------------------------------------------------------
    # 2. Acquire concurrency slot
    # ------------------------------------------------------------------
    acquired = _semaphore.acquire(timeout=2)
    if not acquired:
        return _error("invalid_request",
                       "Execution capacity exhausted on this replica. Retry shortly or wait for autoscaling.")

    exec_dir = None
    try:
        # --------------------------------------------------------------
        # 3. Prepare temporary workspace
        # --------------------------------------------------------------
        exec_id  = uuid.uuid4().hex[:12]
        exec_dir = os.path.join(_EXEC_BASE_DIR, f"exec_{exec_id}")
        os.makedirs(exec_dir, exist_ok=True)

        main_py = os.path.join(exec_dir, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(code)

        # --------------------------------------------------------------
        # 4. Execute in subprocess
        # --------------------------------------------------------------
        stdin_bytes = stdin.encode("utf-8", errors="replace")
        env = _clean_env()

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [_PYTHON_BIN, "-u", main_py],
                input=stdin_bytes,
                capture_output=True,
                timeout=timeout,
                cwd=exec_dir,
                env=env,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            stdout_raw = exc.stdout or b""
            stderr_raw = exc.stderr or b""
            stdout_str, stdout_trunc = _truncate(stdout_raw, MAX_STDOUT_BYTES)
            stderr_str, stderr_trunc = _truncate(stderr_raw, MAX_STDERR_BYTES)
            return {
                "status": "time_limit_exceeded",
                "exit_code": None,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "execution_time_ms": round(elapsed_ms, 2),
                "timed_out": True,
                "stdout_truncated": stdout_trunc,
                "stderr_truncated": stderr_trunc,
            }

        # --------------------------------------------------------------
        # 5. Process results
        # --------------------------------------------------------------
        stdout_str, stdout_trunc = _truncate(proc.stdout, MAX_STDOUT_BYTES)
        stderr_str, stderr_trunc = _truncate(proc.stderr, MAX_STDERR_BYTES)

        if proc.returncode == 0:
            status = "success"
        elif proc.returncode < 0:
            # Killed by signal (e.g. OOM killer sends SIGKILL = -9)
            sig = -proc.returncode
            if sig == 9:
                status = "memory_limit_exceeded"
                stderr_str = (stderr_str or "") + f"\n[Process killed by signal {sig} — likely exceeded memory limit]"
            else:
                status = "runtime_error"
                stderr_str = (stderr_str or "") + f"\n[Process killed by signal {sig}]"
        else:
            status = "runtime_error"

        return {
            "status": status,
            "exit_code": proc.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "execution_time_ms": round(elapsed_ms, 2),
            "timed_out": timed_out,
            "stdout_truncated": stdout_trunc,
            "stderr_truncated": stderr_trunc,
        }

    except Exception as exc:
        return _error("runtime_error", f"Execution infrastructure error: {str(exc)}")

    finally:
        # --------------------------------------------------------------
        # 6. Cleanup
        # --------------------------------------------------------------
        if exec_dir and os.path.isdir(exec_dir):
            try:
                shutil.rmtree(exec_dir, ignore_errors=True)
            except Exception:
                pass
        _semaphore.release()


def _error(status: str, message: str):
    """Helper to build a structured error response."""
    return {
        "status": status,
        "exit_code": None,
        "stdout": "",
        "stderr": message,
        "execution_time_ms": 0.0,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
