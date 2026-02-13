# Product Requirements Document (PRD)
## Appointment Booking AI Chatbot (Take-Home Prototype)

---

## 1. Objective
Build a simplified end-to-end AI chatbot that supports appointment booking.  
The goal is to demonstrate:
- Conversational flow design
- Scheduling and booking logic
- Clean service boundaries
- Practical, scalable AI integration

This is a prototype for evaluation. Production hardening and full feature coverage are out of scope.

---

## 2. Architecture (Locked)
The system must follow a service-oriented architecture with clear boundaries:

- **Frontend (Next.js)**  
  - UI only (authentication pages + chat UI)
  - No business logic or AI orchestration

- **Backend API (Node.js + Express)**  
  - Authentication (JWT)
  - Short-lived chat token issuance
  - Validation, logging, rate limiting
  - Gateway to AI microservice
  - No AI logic

- **AI Microservice (FastAPI + LangChain)**  
  - Conversational orchestration
  - Multi-turn memory
  - Slot-filling + booking workflow
  - Availability checks
  - Appointment creation/updating
  - State persistence

- **Database (PostgreSQL)**  
  - Persistent storage for users, chat sessions, appointments

All services must be runnable locally using Docker Compose.

---

## 3. Core User Workflow (Booking)
1. User authenticates via frontend.
2. User opens chat session.
3. User requests an appointment.
4. AI collects missing details (date, time, timezone, service type).
5. AI checks availability (simulated).
6. If unavailable, AI proposes alternatives.
7. On success, AI creates an appointment record.
8. AI confirms booking and persists conversation state.

The system must support multi-turn conversations and recover gracefully from incomplete or ambiguous input.

---

## 4. Technology Constraints (Locked)
- Frontend: React or Next.js (Next.js preferred)
- API: Node.js + Express
- AI: Python + FastAPI + LangChain
- Database: PostgreSQL
- Orchestration: Docker Compose
- Authentication: JWT
- AI Provider: OpenAI/Anthropic/open-source (pluggable; fallback allowed)

---

## 5. Data Model (High-Level)
- **users**: user profiles + auth
- **appointments**: scheduling data + status
- **chat_sessions**: conversation logs + extracted state (JSONB)

Indexes should support:
- User-based lookups
- Time-based appointment queries
- Recent chat session retrieval

Multi-tenancy (`business_id`) may be documented but is optional to implement.

---

## 6. State & Conversation Design
- Conversations must persist state across turns.
- The system must:
  - Ask one targeted follow-up question at a time.
  - Track extracted booking slots.
  - Avoid looping after booking confirmation.
  - Support rescheduling or starting a new booking within a session.

---

## 7. Security & Reliability (Baseline)
- JWT-based authentication
- Short-lived chat tokens for scoped access
- Input validation
- Rate limiting on chat endpoints
- Centralized error handling
- Safe error messages (no stack traces to clients)

---

## 8. Non-Goals
- No real calendar integrations (Google/Outlook)
- No real inventory for hotels/flights
- No WebRTC/telephony implementation
- No production deployment or scalability guarantees

---

## 9. Assumptions
- Appointments are 1-hour slots
- Business hours are Mon–Fri, 09:00–17:00 (UTC)
- Timezone defaults to UTC
- Availability is simulated using database state
- LLM improves extraction; deterministic fallback is acceptable

---

## 10. Evaluation Criteria
The implementation will be evaluated on:
- Clarity of architecture and service boundaries
- Quality of conversational flow and booking logic
- API design and security awareness
- Database modeling and scalability thinking
- Documentation of assumptions and tradeoffs
