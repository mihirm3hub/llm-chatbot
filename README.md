# Full-Stack LLM chatbot (Next.js, Node.js, FastAPI, PostgreSQL, LLM)


This repository contains a small prototype that lets a user book an appointment through a chat interface.

The user can:
- Create an account and sign in
- Open a chat session
- Request an appointment (date and time)
- Receive confirmation when the appointment is booked

## Architecture

The system is split into four services with clear responsibilities:

- Web UI (Next.js)
       - Pages for signup, login, and chat
       - Stores the user token in the browser for this prototype
       - Sends chat messages to the API

- API (Express)
       - User authentication (JWT)
       - Issues a short-lived chat token
       - Validates requests, applies basic rate limits, and forwards chat to the AI service

- AI service (FastAPI)
       - Manages the multi-turn conversation
       - Extracts booking details from user messages
       - Applies deterministic booking rules and writes to the database

- Database (PostgreSQL)
       - Stores users, chat sessions, and appointments

Request flow:

```bash

┌───────────────┐      HTTP      ┌────────────────┐      HTTP      ┌──────────────────┐
│  Web (Next.js)│ ──────────────>│  API (Express) │ ─────────────> │  AI (FastAPI)    │
│  :3000        │                │  :3001         │                │  :8000           │
└──────┬────────┘                └───────┬────────┘                └─────────┬────────┘
       │                                 │                                   │
       │                                 │ SQL                               │ SQL
       │                                 ▼                                   ▼
       │                           ┌────────────────────────────────────────────────┐
       └─────────────────────────> │               Postgres (:5432)                 │
                                   └────────────────────────────────────────────────┘

```

---

Service boundaries are intentional:
- The web app is UI-only.
- The API owns authentication and acts as a gateway.
- The AI service owns conversation state and booking behavior.
- The database is the single source of truth.

## How to run locally

### Prerequisites
- Docker Desktop

### Steps
1) Create a local environment file:

```bash
.env
```

2) (Optional) Configure an LLM key.

The AI service can run with deterministic parsing only, but an LLM key improves understanding of user input.

3) Start the stack:

```bash
docker compose up --build
```

4) Open the app:
- Web UI: http://localhost:3000

### Environment variables

Docker Compose provides internal service URLs. The main values you may set locally are:

- `GEMINI_API_KEY` (optional): enables Gemini-based understanding and response composition in the AI service

These are configured via Docker Compose for local development:

- `JWT_SECRET`: used by the API to sign tokens
- `DATABASE_URL`: used by the API and AI service to connect to Postgres
- `AI_SERVICE_URL`: used by the API to call the AI service

### End-to-end test

1) Sign up in the web UI.
2) Go to the chat page.
3) Send a message like:

```
"Book an appointment next Tuesday at 3pm"
```

You should receive either a clarification question (if details are missing) or a booking confirmation.

## Core workflow

The booking flow is:
1) The user requests an appointment in chat.
2) The AI service extracts the date and time from the message.
3) If information is missing, the assistant asks for one missing detail at a time.
4) When enough details are present, the AI service checks availability (simulated).
5) If available, it creates an appointment record and confirms the booking.
6) The conversation history is stored in the database so the session can continue across requests.

Multi-turn conversations work by storing messages and per-session state in Postgres. Each new chat message loads the prior session data and continues from there.

## Design decisions and tradeoffs

Why separate services:
- It keeps responsibilities clear and easier to test.
- The web app stays simple.
- The API has a single job: auth and safe forwarding.
- The AI service can evolve without touching the API or UI.

Why deterministic booking logic:
- Scheduling rules should be consistent and testable.
- The model is used to understand user text and to phrase responses, but booking decisions are enforced in code.

Why localStorage for auth in this prototype:
- It is simple for a take-home prototype.
- In production this would move to httpOnly cookies, CSRF protection, and tighter session controls.

Why availability is simulated:
- The goal is to demonstrate flow and persistence without relying on external calendar systems.

## Assumptions

- Business hours are Monday to Friday, 09:00–17:00 UTC.
- Appointments are 1-hour slots.
- If a timezone is not provided, times are treated as UTC.
- One active booking flow is tracked per chat session.

## Known limitations

- No real calendar integration (Google Calendar / Outlook).
- No real-time sockets; the UI uses request/response calls.
- Natural language handling is limited for vague phrases (for example, "sometime next week").
- No production deployment or scaling setup.

## Optional demo

If you want to provide a demo, record a short screen capture showing:
1) Signup and login
2) Starting a chat session
3) Booking an appointment end-to-end
4) A follow-up message in the same session to show multi-turn behavior
