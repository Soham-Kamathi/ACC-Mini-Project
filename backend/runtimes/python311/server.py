import sys
import os
import json
import time
import traceback
import importlib
import concurrent.futures
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Ensure current working directory is in sys.path
sys.path.insert(0, os.getcwd())

# Dynamically import user handler module
HANDLER_MODULE_NAME = os.getenv("HANDLER_MODULE", "handler")
HANDLER_FUNC_NAME = os.getenv("HANDLER_FUNCTION", "handler")
TIMEOUT_SECONDS = int(os.getenv("EXECUTION_TIMEOUT", "10"))

user_handler = None

def load_user_handler():
    global user_handler
    try:
        mod = importlib.import_module(HANDLER_MODULE_NAME)
        user_handler = getattr(mod, HANDLER_FUNC_NAME, None) or getattr(mod, "main", None)
        if user_handler is not None:
            print(f"[Runtime] Successfully loaded handler function from {HANDLER_MODULE_NAME}")
        else:
            print(f"[Runtime Error] No '{HANDLER_FUNC_NAME}' or 'main' function found in {HANDLER_MODULE_NAME}")
    except Exception as e:
        print(f"[Runtime Error] Failed to load handler: {e}")
        traceback.print_exc()
        user_handler = None

load_user_handler()

class FunctionRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ready", "runtime": "python311"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/execute":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            
            try:
                if post_data:
                    event = json.loads(post_data.decode("utf-8"))
                else:
                    event = {}
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {str(e)}"}).encode("utf-8"))
                return

            if user_handler is None:
                load_user_handler()
                if user_handler is None:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Handler function could not be loaded"}).encode("utf-8"))
                    return

            start_time = time.perf_counter()
            
            # Execute with timeout in thread pool
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                import inspect
                try:
                    sig = inspect.signature(user_handler)
                    params = list(sig.parameters.values())
                    if len(params) == 0:
                        future = executor.submit(user_handler)
                    elif len(params) == 1:
                        future = executor.submit(user_handler, event)
                    elif isinstance(event, dict) and all(p.name in event for p in params if p.default == inspect.Parameter.empty):
                        future = executor.submit(user_handler, **event)
                    else:
                        future = executor.submit(user_handler, event)
                except Exception:
                    future = executor.submit(user_handler, event)
                try:
                    result = future.result(timeout=TIMEOUT_SECONDS)
                    exec_duration_ms = (time.perf_counter() - start_time) * 1000.0
                    
                    response = {
                        "statusCode": 200,
                        "result": result,
                        "execution_time_ms": round(exec_duration_ms, 2)
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode("utf-8"))
                except concurrent.futures.TimeoutError:
                    exec_duration_ms = (time.perf_counter() - start_time) * 1000.0
                    response = {
                        "statusCode": 504,
                        "error": f"Function execution timed out after {TIMEOUT_SECONDS}s",
                        "execution_time_ms": round(exec_duration_ms, 2)
                    }
                    self.send_response(504)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode("utf-8"))
                except Exception as e:
                    exec_duration_ms = (time.perf_counter() - start_time) * 1000.0
                    response = {
                        "statusCode": 500,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "execution_time_ms": round(exec_duration_ms, 2)
                    }
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Override to log structured info
        sys.stderr.write(f"[Runtime Log] {self.address_string()} - {format % args}\n")

def run_server(port=8080):
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, FunctionRequestHandler)
    print(f"[Runtime] Serverless Function Runner listening on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    run_server(port)
