import json
from datetime import timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .db import init_db, SessionLocal, Submission
from .problems import PROBLEMS, get_problem, public_problem
from .faas_client import invoke, FaaSError
from .harness import prepare_code

app = FastAPI(title="CodeArena API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup(): init_db()

class RunRequest(BaseModel):
    code: str = Field(min_length=1, max_length=65536)
    stdin: str = Field(default="", max_length=1_048_576)

class SubmitRequest(BaseModel):
    code: str = Field(min_length=1, max_length=65536)

def _err(exc): raise HTTPException(status_code=503, detail=str(exc))

@app.get("/api/health")
async def health():
    from .config import settings
    return {"status": "ok", "faas_configured": bool(settings.faas_public_id and settings.faas_api_key)}

@app.get("/api/problems")
async def list_problems(): return [public_problem(p) for p in PROBLEMS]

@app.get("/api/problems/{problem_id}")
async def problem(problem_id: str):
    p = get_problem(problem_id)
    if not p: raise HTTPException(404, "Problem not found")
    return public_problem(p)

@app.post("/api/problems/{problem_id}/run")
async def run(problem_id: str, req: RunRequest):
    if not get_problem(problem_id): raise HTTPException(404, "Problem not found")
    exec_code = prepare_code(problem_id, req.code)
    try: return await invoke(exec_code, req.stdin)
    except FaaSError as exc: _err(exc)

@app.post("/api/problems/{problem_id}/submit")
async def submit(problem_id: str, req: SubmitRequest):
    p = get_problem(problem_id)
    if not p: raise HTTPException(404, "Problem not found")
    results, infra_error = [], None
    public_count = len(p["public_tests"])
    exec_code = prepare_code(problem_id, req.code)
    for index, (stdin, expected) in enumerate(p["public_tests"] + p["hidden_tests"], 1):
        try: result = await invoke(exec_code, stdin)
        except FaaSError as exc: infra_error = str(exc); break
        actual = result["stdout"].strip()
        expected_clean = expected.strip()
        passed = result["status"] == "success" and actual == expected_clean
        is_public = index <= public_count
        results.append({"test_case": index, "input": stdin if is_public else "Hidden test case", "expected": expected_clean if is_public else "",
                        "hidden": not is_public, "actual": actual,
                        "passed": passed, "status": result["status"], "stderr": result["stderr"],
                        "execution_time_ms": result["execution_time_ms"]})
        if result["status"] != "success": break
    if infra_error: _err(infra_error)
    passed_count = sum(1 for x in results if x["passed"])
    total = len(p["public_tests"] + p["hidden_tests"])
    if any(x["status"] == "time_limit_exceeded" for x in results): verdict = "Time Limit Exceeded"
    elif any(x["status"] in ("runtime_error", "memory_limit_exceeded") for x in results): verdict = "Runtime Error"
    elif passed_count == total: verdict = "Accepted"
    else: verdict = "Wrong Answer"
    total_time = sum(float(x["execution_time_ms"] or 0) for x in results)
    db = SessionLocal()
    row = Submission(problem_id=problem_id, code=req.code, verdict=verdict, passed=passed_count, total=total,
                     execution_time_ms=total_time, results_json=json.dumps(results))
    db.add(row); db.commit(); db.refresh(row); db.close()
    return {"id": row.id, "problem_id": problem_id, "verdict": verdict, "passed": passed_count, "total": total,
            "execution_time_ms": total_time, "results": results}

@app.get("/api/submissions")
async def submissions():
    db = SessionLocal(); rows = db.query(Submission).order_by(Submission.created_at.desc()).all(); out = []
    for r in rows:
        p = get_problem(r.problem_id)
        out.append({"id": r.id, "problem_id": r.problem_id, "problem_title": p["title"] if p else r.problem_id,
                    "verdict": r.verdict, "passed": r.passed, "total": r.total, "execution_time_ms": r.execution_time_ms,
                    "created_at": r.created_at.isoformat()})
    db.close(); return out

@app.get("/api/submissions/{submission_id}")
async def submission(submission_id: int):
    db = SessionLocal(); row = db.get(Submission, submission_id); db.close()
    if not row: raise HTTPException(404, "Submission not found")
    return {"id": row.id, "problem_id": row.problem_id, "verdict": row.verdict, "passed": row.passed, "total": row.total,
            "execution_time_ms": row.execution_time_ms, "code": row.code, "results": json.loads(row.results_json)}

