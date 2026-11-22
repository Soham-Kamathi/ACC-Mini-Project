# CodeArena

CodeArena is a LeetCode-style React/FastAPI client for the existing custom FaaS platform in `../`. It never executes student code locally. Every Run and Submit invocation is proxied by `backend/app/faas_client.py` to the FaaS public endpoint.

## Setup

1. Copy `backend/.env.example` to `backend/.env` and fill in `FAAS_BASE_URL`, `FAAS_PUBLIC_ID`, and `FAAS_API_KEY`.
2. In a terminal: `cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt; .venv\Scripts\uvicorn app.main:app --port 8001`.
3. In another terminal: `cd frontend; npm install; npm run dev`.
4. Open `http://localhost:5174`.

The FaaS public function should be the existing Python code executor handler. Its public request contract is `{language, code, stdin, timeout_seconds}`; the backend sends this contract with `X-API-Key` and normalizes the returned telemetry.

Hidden tests are kept in the backend problem repository and are never returned by the problem endpoints. Submission records are stored in `backend/codearena.db`.
