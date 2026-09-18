# Quantum Key Distribution (QKD)

FastAPI backend + Vite React frontend for simulating QKD protocols (BB84, E91), attacks, and ML models over the results.

## Structure

```
backend/
  app/
    main.py          FastAPI app, CORS, router registration
    routers/         REST endpoints (health, ...)
    protocols/       QKD protocol implementations (BB84, E91, ...)
    attacks/         Attack simulations (intercept-resend, PNS, ...)
    ml/              ML models over simulation data
    models.py        SQLAlchemy engine/session/models
    auth.py          Auth scaffolding (JWT-ready stub)
    websocket.py     WebSocket manager for live run updates
  requirements.txt
  Dockerfile
frontend/            Vite + React (JavaScript, plain CSS)
docker-compose.yml   backend + Postgres
```

## Run locally (no Docker)

**Backend** (Python 3.11+):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000 (health: http://localhost:8000/health)
- Swagger docs: http://localhost:8000/docs

The backend defaults to `postgresql+psycopg://qkd:qkd@localhost:5432/qkd`. Without a database running, `/health` reports `"database": "error: ..."` and status `"degraded"` — the API still works. To run Postgres only:

```bash
docker compose up -d db
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev
```

- App: http://localhost:5173 — fetches `/health` from the backend and shows the status.

## Run with Docker

```bash
docker compose up --build
```

- Backend: http://localhost:8000
- Postgres: localhost:5432 (user/pass/db: `qkd`/`qkd`/`qkd`)

Then run the frontend dev server as above (`cd frontend && npm run dev`).

## Configuration

| Variable | Where | Default |
| --- | --- | --- |
| `DATABASE_URL` | backend | `postgresql+psycopg://qkd:qkd@localhost:5432/qkd` |
| `JWT_SECRET` | backend | **required** — no default; the API refuses to start without it |
| `VITE_API_BASE` | frontend | `http://localhost:8000` |

CORS is pre-configured for `http://localhost:5173` / `4173`.

## Authentication

- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
- Passwords are bcrypt-hashed (passlib). On login the token is a JWT stored in
  an **httpOnly cookie** — never localStorage — and backed by a `user_sessions`
  row so logout revokes server-side.
- Wrong-email and wrong-password logins both run one bcrypt comparison against
  a dummy hash, so response timing does not leak whether an email is registered.
- `/auth/login` and `/auth/register` are rate-limited (slowapi, per-IP).

Generate a secret and put it in `backend/.env` (see `backend/.env.example`):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

When running the backend container via docker-compose, export `JWT_SECRET` in
your shell (or a compose `.env` file) — the compose file refuses to start the
backend without it.

## Troubleshooting: folder names containing `:`

This project currently lives in a folder whose name contains a colon
(`project 26:9`). `:` is the PATH separator, which breaks several tools:

- `python3 -m venv` refuses to create a venv inside the project
- `npm run <script>` fails (`vite: command not found`) because npm's PATH gets split
- Vite's dev server 403s on `index.html` (mitigated via `server.fs.strict: false` in `vite.config.js`)

Recommended fix: rename the folder without a colon (e.g. `qkd-project`).
Meanwhile: create venvs outside the project (e.g. `python3 -m venv /tmp/qkd-venv`)
and run vite via `./node_modules/.bin/vite` instead of `npm run dev`.

`docker-compose.yml` is provided but has not been executed on the current
machine (no Docker daemon installed).
