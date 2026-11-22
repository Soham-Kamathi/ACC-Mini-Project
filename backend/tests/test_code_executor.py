"""
Functional tests for the Python Code Execution handler.

These tests import the handler directly and exercise it in-process (no Pod
required).  The handler's subprocess execution still runs real Python
subprocesses, so the tests validate the full code-exec pipeline except
for the Kubernetes isolation layer.

Run with:
    python -m pytest backend/tests/test_code_executor.py -v
"""

import sys
import os
import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so the handler can be imported
# when pytest is invoked from the project root.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "backend", "runtimes", "python311")
if RUNTIME_DIR not in sys.path:
    sys.path.insert(0, RUNTIME_DIR)

from code_executor_handler import handler  # noqa: E402


# ===================================================================
# Functional tests
# ===================================================================

class TestBasicExecution:
    """Simple programs that should succeed."""

    def test_hello_world(self):
        result = handler({
            "language": "python",
            "code": 'print("hello")',
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert result["stdout"].strip() == "hello"
        assert result["timed_out"] is False

    def test_stdin_reading(self):
        result = handler({
            "language": "python",
            "code": "name = input()\nprint(f'Hi {name}')",
            "stdin": "Alice",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        assert "Hi Alice" in result["stdout"]

    def test_stdin_numbers(self):
        result = handler({
            "language": "python",
            "code": "a, b = map(int, input().split())\nprint(a + b)",
            "stdin": "10 20",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        assert result["stdout"].strip() == "30"

    def test_multi_line_output(self):
        result = handler({
            "language": "python",
            "code": "for i in range(10):\n    print(i)",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        lines = result["stdout"].strip().splitlines()
        assert len(lines) == 10
        assert lines[0] == "0"
        assert lines[9] == "9"

    def test_no_output(self):
        result = handler({
            "language": "python",
            "code": "x = 42",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert result["stdout"] == ""

    def test_stderr_output(self):
        result = handler({
            "language": "python",
            "code": "import sys\nsys.stderr.write('warning\\n')\nprint('ok')",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        assert "ok" in result["stdout"]
        assert "warning" in result["stderr"]


# ===================================================================
# Error handling tests
# ===================================================================

class TestErrors:
    """Programs that should produce runtime errors."""

    def test_division_by_zero(self):
        result = handler({
            "language": "python",
            "code": "print(1 / 0)",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "runtime_error"
        assert result["exit_code"] != 0
        assert "ZeroDivisionError" in result["stderr"]

    def test_syntax_error(self):
        result = handler({
            "language": "python",
            "code": "def (",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "runtime_error"
        assert result["exit_code"] != 0
        assert "SyntaxError" in result["stderr"]

    def test_import_error(self):
        result = handler({
            "language": "python",
            "code": "import nonexistent_module_xyz",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "runtime_error"
        assert "ModuleNotFoundError" in result["stderr"]

    def test_name_error(self):
        result = handler({
            "language": "python",
            "code": "print(undefined_variable_xyz)",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "runtime_error"
        assert "NameError" in result["stderr"]

    def test_runtime_exception_with_stderr(self):
        """A program that prints to both stdout and stderr before crashing."""
        result = handler({
            "language": "python",
            "code": "print('before')\nraise ValueError('boom')",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "runtime_error"
        assert "before" in result["stdout"]
        assert "ValueError" in result["stderr"]
        assert "boom" in result["stderr"]


# ===================================================================
# Validation tests
# ===================================================================

class TestValidation:
    """Requests that should be rejected before execution."""

    def test_missing_language(self):
        result = handler({
            "code": "print(1)",
            "stdin": "",
        })
        assert result["status"] == "invalid_request"
        assert "language" in result["stderr"].lower()

    def test_unsupported_language(self):
        result = handler({
            "language": "java",
            "code": "System.out.println(1);",
            "stdin": "",
        })
        assert result["status"] == "invalid_request"
        assert "unsupported" in result["stderr"].lower()

    def test_empty_code(self):
        result = handler({
            "language": "python",
            "code": "",
            "stdin": "",
        })
        assert result["status"] == "invalid_request"

    def test_missing_code(self):
        result = handler({
            "language": "python",
            "stdin": "",
        })
        assert result["status"] == "invalid_request"

    def test_non_dict_event(self):
        result = handler("not a dict")
        assert result["status"] == "invalid_request"

    def test_code_too_large(self):
        big_code = "x = 1\n" * 20000  # well over 64 KB
        result = handler({
            "language": "python",
            "code": big_code,
            "stdin": "",
        })
        assert result["status"] == "invalid_request"
        assert "size" in result["stderr"].lower()


# ===================================================================
# Timeout tests
# ===================================================================

class TestTimeout:
    """Programs that should be killed for exceeding the time limit."""

    def test_infinite_loop(self):
        result = handler({
            "language": "python",
            "code": "while True: pass",
            "stdin": "",
            "timeout_seconds": 1,
        })
        assert result["status"] == "time_limit_exceeded"
        assert result["timed_out"] is True
        assert result["execution_time_ms"] >= 900  # at least ~1s

    def test_sleep_exceeds_timeout(self):
        result = handler({
            "language": "python",
            "code": "import time\ntime.sleep(10)\nprint('done')",
            "stdin": "",
            "timeout_seconds": 1,
        })
        assert result["status"] == "time_limit_exceeded"
        assert result["timed_out"] is True

    def test_timeout_clamped_to_max(self):
        """timeout_seconds beyond MAX_TIMEOUT is clamped, not rejected."""
        result = handler({
            "language": "python",
            "code": "print('ok')",
            "stdin": "",
            "timeout_seconds": 999,
        })
        assert result["status"] == "success"

    def test_timeout_clamped_to_min(self):
        """timeout_seconds below MIN_TIMEOUT is clamped to 1."""
        result = handler({
            "language": "python",
            "code": "print('ok')",
            "stdin": "",
            "timeout_seconds": 0,
        })
        assert result["status"] == "success"


# ===================================================================
# Output limit tests
# ===================================================================

class TestOutputLimits:
    """Programs that produce very large output."""

    def test_large_stdout_truncated(self):
        # Each line is ~52 bytes; 25000 lines ≈ 1.3 MB > 1 MB limit
        result = handler({
            "language": "python",
            "code": "for i in range(25000):\n    print('x' * 50)",
            "stdin": "",
            "timeout_seconds": 10,
        })
        # Should still succeed (exit code 0) but stdout may be truncated
        assert result["status"] == "success"
        assert result["stdout_truncated"] is True
        assert len(result["stdout"]) <= 1024 * 1024 + 100  # allow small overshoot from decoding

    def test_large_stderr_truncated(self):
        result = handler({
            "language": "python",
            "code": "import sys\nfor i in range(10000):\n    sys.stderr.write('e' * 50 + '\\n')\nprint('done')",
            "stdin": "",
            "timeout_seconds": 10,
        })
        assert result["stderr_truncated"] is True


# ===================================================================
# Timing and metadata tests
# ===================================================================

class TestMetadata:
    """The response carries correct metadata."""

    def test_execution_time_reported(self):
        result = handler({
            "language": "python",
            "code": "import time\ntime.sleep(0.1)\nprint('done')",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["status"] == "success"
        assert result["execution_time_ms"] >= 80  # at least ~100ms

    def test_exit_code_on_success(self):
        result = handler({
            "language": "python",
            "code": "print('ok')",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["exit_code"] == 0

    def test_exit_code_on_error(self):
        result = handler({
            "language": "python",
            "code": "raise Exception('fail')",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["exit_code"] == 1

    def test_exit_code_on_sys_exit(self):
        result = handler({
            "language": "python",
            "code": "import sys\nsys.exit(42)",
            "stdin": "",
            "timeout_seconds": 5,
        })
        assert result["exit_code"] == 42
        assert result["status"] == "runtime_error"
