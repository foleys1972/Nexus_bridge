# NexusBridge Command Center

## Dev (local)

1. Copy `.env.example` to `.env` and set values.

### Frontend

- Install dependencies:
  - `npm install`
- Run frontend:
  - `npm run dev:frontend`

### Backend (Python)

- Run backend:
  - `python -m venv .venv`
  - activate venv
  - `pip install -r apps/backend-python/requirements.txt`
  - `uvicorn app.main:app --host 0.0.0.0 --port 3000`

## Docker

- `docker compose --env-file .env up --build`
