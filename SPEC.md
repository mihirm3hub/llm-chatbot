PRD: Appointment Booking AI Chatbot (Take-Home Prototype)

Goal
Build a minimal end-to-end AI chatbot that supports appointment booking with clean service boundaries:
- Frontend: Next.js chat UI + signup/login
- Backend: Node.js/Express API with JWT auth, /api/chatbot/token, validation/logging/rate-limiting, and a gateway endpoint to a Python AI microservice
- AI microservice: Python FastAPI + LangChain for multi-turn booking workflow, storing conversation state and appointments in Postgres
- Database: Postgres schema for users, appointments, chat_sessions with sample seed data and indexes

Non-goals
- Fancy UI polish
- Production scaling, Kubernetes, Redis clusters, etc.
- WebRTC/voice/telephony (mention future extension only)

High-level architecture
1) User signs up/logs in via Express API → receives JWT
2) Frontend uses JWT to request short-lived chatbot token via POST /api/chatbot/token
3) Frontend sends chat messages to Express POST /api/chat (or /api/chat/messages) with {session_id, message} and Authorization: Bearer <jwt>
4) Express validates + rate-limits + logs request, then forwards to Python AI service POST /chat with {user_id, session_id, message}
5) Python service uses LangChain to:
   - read prior session state/messages from Postgres
   - run a booking chain that slot-fills required fields
   - if missing info, asks a targeted follow-up question
   - if sufficient info, checks/simulates availability and creates/updates appointment record
   - appends interaction to chat_sessions messages log
6) Python returns assistant response + structured state (optional) to Express, which returns it to frontend

Core user stories
US1: Signup/Login
- As a user, I can sign up with email/password and log in to get a JWT.
Acceptance: JWT is issued; invalid credentials return 401; passwords are hashed.

US2: Start chat session
- As a logged-in user, I can open chat page and start a new session.
Acceptance: client creates session_id (UUID) and can chat successfully.

US3: Book appointment conversationally
- As a user, I can say: “Book a meeting next Tuesday at 3pm”
- Assistant asks for missing details (service type, timezone, name if needed)
- Assistant confirms booking and stores appointment
Acceptance: appointment row created with status=BOOKED; assistant confirms with date/time.

US4: Handle ambiguity/incomplete input
- If user says “tomorrow afternoon” or “next week”, assistant asks clarifying questions.
Acceptance: assistant does not hallucinate a final time; it requests clarification.

US5: View current booking (optional)
- User can ask “What did I book?” and assistant replies using stored appointment.
Acceptance: assistant fetches latest appointment for user and summarizes.

API contracts

Express API (Node)
- POST /api/auth/signup
  body: {email, password}
  returns: {jwt}
- POST /api/auth/login
  body: {email, password}
  returns: {jwt}
- POST /api/chatbot/token
  auth: Bearer jwt
  returns: {chat_token, expires_in_seconds}
  Notes: chat_token can just be a short-lived JWT with scope=chat and session/user binding.
- POST /api/chat
  auth: Bearer jwt
  body: {session_id, message}
  returns: {reply, session_id}

Python AI service (FastAPI)
- POST /chat
  body: {user_id, session_id, message}
  returns: {reply, session_id, extracted_slots?, appointment_id?}

Booking workflow requirements (LangChain)
- Required slots (minimal):
  - intent: booking vs inquiry
  - date (ISO date)
  - time (HH:MM)
  - timezone (default UTC if not provided; document assumption)
  - service_type (default “general” if not provided; or ask)
- Flow rules:
  - If intent not booking, answer normally but keep state.
  - If booking intent and slots missing → ask one clear question at a time.
  - When enough slots → check availability (simulate):
      - For simplicity: available if slot is on the hour between 09:00–17:00 Mon–Fri and not already booked.
  - Create appointment with status=BOOKED and store confirmation.
  - If slot unavailable → propose 2 alternative times.

State/memory
- Persist conversation messages in Postgres table chat_sessions as JSONB array, plus metadata (created_at, updated_at).
- Also persist “current slots” per session (can be JSONB in chat_sessions.metadata or a separate table).
- Avoid in-memory-only storage so service restarts do not lose context.

Logging
- Log each message with timestamp, user_id, session_id, role (user/assistant), and optional latency_ms.
- Store in chat_sessions.messages JSONB; also print concise logs to console.

Database schema (Postgres)
Tables:
1) users
- id (uuid pk)
- email (unique)
- password_hash
- created_at
Indexes: unique(email)

2) appointments
- id (uuid pk)
- user_id (fk users.id)
- start_time (timestamptz)
- end_time (timestamptz, optional)
- service_type (text)
- status (text: BOOKED/CANCELLED)
- created_at
Indexes:
- (user_id, start_time)
- (start_time)

3) chat_sessions
- id (uuid pk) OR session_id text/uuid
- user_id (fk users.id)
- messages (jsonb)  // [{role, content, ts}]
- metadata (jsonb)  // {slots:{...}}
- created_at, updated_at
Indexes:
- (user_id, id)
Optional: business_id column for multi-tenancy (not required)

Security requirements
- JWT auth on Express endpoints
- Password hashing with bcrypt/argon2
- Basic rate limiting on /api/chat and /api/chatbot/token
- Input validation for payloads
- Proper error handler returning JSON with safe messages (no stack traces)

Frontend requirements
- Minimal pages: /signup, /login, /chat
- Chat UI: message list, input box, send button, loading indicator
- Maintain session_id in local state; keep messages in state
- Polling is OK:
   - on send: call POST /api/chat and append reply
- Store JWT securely (prefer httpOnly cookie; if using localStorage, document tradeoff)

DevEx + local run
- Provide docker-compose.yml with services: web, api, ai, db
- Provide .env.example with required env vars:
   - DB connection string for api + ai
   - JWT_SECRET for api
   - OPENAI_API_KEY for ai
   - AI_SERVICE_URL for api -> ai
- README must include:
   - architecture diagram (ASCII ok)
   - how to run locally
   - tradeoffs and assumptions
   - known limitations

Acceptance criteria checklist
- docker compose up brings system up
- user can signup/login and reach chat page
- user can book an appointment via multi-turn chat
- appointment stored in Postgres
- chat history persisted per session
- middleware present: validation, logging, rate limiting, error handling
- clear README with decisions + limitations
