# TeraLeads Appointment Chatbot (Take-Home Prototype)

Minimal end-to-end appointment booking chatbot with clean service boundaries.

## Architecture

```text
┌───────────────┐        JWT (user)        ┌────────────────────┐
│  Web (Next.js)│ ───────────────────────▶ │  API (Express)     │
│  :3000        │                          │  :3001             │
└──────┬────────┘                          └─────────┬──────────┘
       │                                             │
       │                                             │ forwards chat (later)
       │ short-lived chat token (scope=chat)         ▼
       │                                     ┌────────────────────┐
       └───────────────────────────────────▶ │  AI (FastAPI)       │
                                             │  :8000              │
                                             └─────────┬──────────┘
                                                       │
                                                       ▼
                                             ┌────────────────────┐
                                             │  Postgres           │
                                             │  :5432              │
                                             └────────────────────┘
```

Services are started via Docker Compose:
- `web`: Next.js App Router UI
- `api`: Node.js + Express (auth, tokens, chat gateway)
- `ai`: Python + FastAPI + LangChain (multi-turn booking)
- `db`: Postgres (users, appointments, chat_sessions)

## Local setup (Docker)

1) Create `.env` from the example and add your key:

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`.

2) Start everything:

```bash
docker compose up --build
```

3) Open:
- Web UI: `http://localhost:3000`
- API: `http://localhost:3001`
- AI: `http://localhost:8000`

## Environment variables

Docker Compose wires most config internally. The only required local variable is:
- `OPENAI_API_KEY` (used by the AI service)

The API service also uses:
- `JWT_SECRET` (set in `docker-compose.yml` as a dev value)

## API contracts

Base URL (local): `http://localhost:3001`

### Auth

`POST /api/auth/signup`

Request:
```json
{ "email": "user@example.com", "password": "password123" }
```

Response:
```json
{ "jwt": "<user_jwt>" }
```

`POST /api/auth/login`

Request:
```json
{ "email": "user@example.com", "password": "password123" }
```

Response:
```json
{ "jwt": "<user_jwt>" }
```

### Chatbot token

`POST /api/chatbot/token`

Headers: `Authorization: Bearer <user_jwt>`

Request:
```json
{ "session_id": "<uuid>" }
```

Response:
```json
{ "chat_token": "<chat_jwt>", "expires_in_seconds": 300 }
```

The chat token is short-lived and scoped to `{ user_id, session_id }`.

### Chat (stub)

`POST /api/chat`

Headers: `Authorization: Bearer <user_jwt>`

Request:
```json
{ "session_id": "<uuid>", "message": "hello" }
```

Response:
```json
{ "reply": "stub", "session_id": "<uuid>" }
```

## Data model

Postgres schema is in `db/schema.sql` and includes:
- `users` (UUID pk, unique email)
- `appointments` (UUID pk, fk to users, `timestamptz` start/end, status)
- `chat_sessions` (UUID pk, fk to users, `messages`/`metadata` as JSONB)

## Design decisions

- No ORM: direct `pg` queries for clarity.
- JWT auth for API endpoints; short-lived chat token for future AI gateway.
- Zod request validation on JSON bodies.
- Centralized error handling with safe JSON responses.
- Rate limiting on chat-related endpoints only.
- CORS restricted to `http://localhost:3000`.

## Assumptions

- App runs locally via Docker Compose.
- Timezone defaults and booking workflow behavior follow `SPEC.md`.

## Known limitations

- `POST /api/chat` currently returns a stub reply and does not forward to the AI service yet.
- No production hardening (e.g., cookie-based auth, CSRF protection, structured logging, migrations).

## Reference

See `SPEC.md` for product requirements and acceptance criteria.
