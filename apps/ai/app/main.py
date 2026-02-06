import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from psycopg2.extras import Json

try:
    from langchain.chat_models import ChatOpenAI  # langchain<0.1
except Exception:  # pragma: no cover
    ChatOpenAI = None

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai")

DATABASE_URL = os.environ.get("DATABASE_URL")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class ChatRequest(BaseModel):
    user_id: uuid.UUID
    session_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    session_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    extracted_slots: dict | None = None


def _db_conn():
    if not DATABASE_URL:
        raise RuntimeError("Missing DATABASE_URL")
    return psycopg2.connect(DATABASE_URL)


def _utc_iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _load_session(conn, session_id: uuid.UUID):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT user_id, messages, metadata FROM chat_sessions WHERE id = %s",
            (str(session_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        user_id, messages, metadata = row
        return {
            "user_id": uuid.UUID(str(user_id)),
            "messages": messages or [],
            "metadata": metadata or {},
        }


def _ensure_session(conn, user_id: uuid.UUID, session_id: uuid.UUID):
    existing = _load_session(conn, session_id)
    if existing:
        if existing["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Session does not belong to user")
        return existing

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE id = %s", (str(user_id),))
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=400,
                detail="Unknown user_id; user must be created via API",
            )

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_sessions (id, user_id, messages, metadata)
            VALUES (%s, %s, '[]'::jsonb, '{}'::jsonb)
            """,
            (str(session_id), str(user_id)),
        )
    conn.commit()
    return {"user_id": user_id, "messages": [], "metadata": {}}


def _save_session(conn, session_id: uuid.UUID, messages: list, metadata: dict):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_sessions SET messages = %s, metadata = %s WHERE id = %s",
            (Json(messages), Json(metadata), str(session_id)),
        )
    conn.commit()


def _get_slots(metadata: dict) -> dict:
    slots = metadata.get("slots")
    if isinstance(slots, dict):
        return slots
    return {}


def _merge_slots(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for key, value in (incoming or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_slots_with_langchain(message: str, existing_slots: dict) -> dict:
    if ChatOpenAI is None:
        return {}

    if not os.environ.get("OPENAI_API_KEY"):
        return {}

    llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    system = (
        "You extract appointment-booking slots from a single user message. "
        "Return ONLY a JSON object with keys: intent, date, time, timezone, service_type. "
        "Use null for unknown. intent must be 'booking' or 'inquiry'. "
        "date format: YYYY-MM-DD. time format: HH:MM (24h). timezone: IANA name or UTC. "
        "Do not include any extra keys or commentary."
    )
    user = {
        "message": message,
        "existing_slots": existing_slots or {},
    }

    result = llm.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ]
    )
    content = getattr(result, "content", None) or str(result)
    parsed = _extract_json_object(content)
    if not parsed:
        return {}
    return {
        "intent": parsed.get("intent"),
        "date": parsed.get("date"),
        "time": parsed.get("time"),
        "timezone": parsed.get("timezone"),
        "service_type": parsed.get("service_type"),
    }


def _extract_slots_fallback(message: str) -> dict:
    text = message.strip()

    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    date_str = date_match.group(1) if date_match else None

    time_24_match = re.search(r"\b((?:[01]\d|2[0-3])):([0-5]\d)\b", text)
    time_str = None
    if time_24_match:
        time_str = f"{time_24_match.group(1)}:{time_24_match.group(2)}"
    else:
        time_12_match = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", text, flags=re.IGNORECASE)
        if time_12_match:
            hour = int(time_12_match.group(1))
            minute = int(time_12_match.group(2) or "0")
            ampm = time_12_match.group(3).lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            time_str = f"{hour:02d}:{minute:02d}"

    tz_match = re.search(r"\b([A-Za-z]+/[A-Za-z_]+)\b", text)
    tz_name = tz_match.group(1) if tz_match else None
    if not tz_name:
        if re.search(r"\bUTC\b", text, flags=re.IGNORECASE):
            tz_name = "UTC"
        elif re.search(r"\bGMT\b", text, flags=re.IGNORECASE):
            tz_name = "UTC"

    service_type = None
    svc_match = re.search(r"\b(service|type)\s*[:=]\s*([A-Za-z][A-Za-z0-9_-]{1,30})\b", text, flags=re.IGNORECASE)
    if svc_match:
        service_type = svc_match.group(2).lower()

    return {
        "date": date_str,
        "time": time_str,
        "timezone": tz_name,
        "service_type": service_type,
    }


def _infer_intent_fallback(message: str) -> str:
    msg = message.lower()
    if any(w in msg for w in ["book", "schedule", "appointment", "meeting", "reserve"]):
        return "booking"
    return "inquiry"


def _is_explicit_cancel(message: str) -> bool:
    msg = message.lower().strip()
    return any(
        phrase in msg
        for phrase in [
            "cancel",
            "never mind",
            "nevermind",
            "stop",
            "forget it",
        ]
    )


def _parse_local_start(slots: dict) -> tuple[datetime, str]:
    date_str = slots.get("date")
    time_str = slots.get("time")
    tz_name = (slots.get("timezone") or "UTC").strip() if isinstance(slots.get("timezone"), str) else "UTC"
    service_tz = tz_name or "UTC"

    try:
        tzinfo = ZoneInfo(service_tz)
    except Exception:
        tzinfo = ZoneInfo("UTC")
        service_tz = "UTC"

    local_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    local_time = datetime.strptime(time_str, "%H:%M").time()
    local_dt = datetime.combine(local_date, local_time).replace(tzinfo=tzinfo)
    return local_dt, service_tz


def _within_business_rules(local_dt: datetime) -> bool:
    if local_dt.weekday() >= 5:
        return False
    if local_dt.minute != 0:
        return False
    if not (9 <= local_dt.hour <= 17):
        return False
    return True


def _is_already_booked(conn, start_time_utc: datetime) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM appointments WHERE start_time = %s AND status = 'BOOKED' LIMIT 1",
            (start_time_utc,),
        )
        return cur.fetchone() is not None


def _find_alternatives(conn, local_dt: datetime, tz_name: str, limit: int = 2) -> list[datetime]:
    tzinfo = ZoneInfo(tz_name)
    candidates: list[datetime] = []
    cursor = local_dt
    for _ in range(72):
        cursor = cursor + timedelta(hours=1)
        cursor = cursor.astimezone(tzinfo)
        if not _within_business_rules(cursor):
            continue
        if _is_already_booked(conn, cursor.astimezone(UTC)):
            continue
        candidates.append(cursor)
        if len(candidates) >= limit:
            break
    return candidates


def _create_appointment(conn, user_id: uuid.UUID, start_time_utc: datetime, service_type: str) -> uuid.UUID:
    end_time_utc = start_time_utc + timedelta(minutes=30)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO appointments (user_id, start_time, end_time, service_type, status)
            VALUES (%s, %s, %s, %s, 'BOOKED')
            RETURNING id
            """,
            (str(user_id), start_time_utc, end_time_utc, service_type),
        )
        appointment_id = cur.fetchone()[0]
    conn.commit()
    return uuid.UUID(str(appointment_id))


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    try:
        conn = _db_conn()
    except Exception as exc:
        logger.exception("db_connect_failed")
        raise HTTPException(status_code=500, detail="Database unavailable") from exc

    try:
        session = _ensure_session(conn, payload.user_id, payload.session_id)
        messages = list(session["messages"] or [])
        metadata = dict(session["metadata"] or {})
        slots = _get_slots(metadata)

        cancelled = _is_explicit_cancel(payload.message)

        extracted = _extract_slots_with_langchain(payload.message, slots)
        fallback = _extract_slots_fallback(payload.message)
        extracted = _merge_slots(extracted or {}, fallback)

        existing_intent = slots.get("intent")
        if cancelled:
            extracted["intent"] = "inquiry"
        elif existing_intent == "booking":
            extracted["intent"] = "booking"
        elif existing_intent == "inquiry":
            if extracted.get("intent") == "booking":
                extracted["intent"] = "booking"
            else:
                extracted["intent"] = "inquiry"
        elif not extracted.get("intent"):
            extracted["intent"] = _infer_intent_fallback(payload.message)

        merged_slots = _merge_slots(slots, extracted)
        merged_slots.setdefault("timezone", "UTC")
        merged_slots.setdefault("service_type", "general")
        if cancelled:
            merged_slots.pop("date", None)
            merged_slots.pop("time", None)
            merged_slots.pop("appointment_id", None)

        user_msg = {"role": "user", "content": payload.message, "ts": _utc_iso_now()}
        messages.append(user_msg)

        reply_text: str
        appointment_id: uuid.UUID | None = None

        if cancelled:
            reply_text = "Okay - cancelled. If you'd like to book, tell me the date and time you want."
        elif merged_slots.get("intent") != "booking":
            reply_text = "I can help you book an appointment. Tell me the date and time you want."
        else:
            if not merged_slots.get("date"):
                reply_text = "What date would you like to book? (YYYY-MM-DD)"
            elif not merged_slots.get("time"):
                reply_text = "What time would you like? (HH:MM, 24-hour)"
            else:
                try:
                    local_dt, tz_name = _parse_local_start(merged_slots)
                except Exception:
                    reply_text = "I couldn't parse that date/time. Please provide date as YYYY-MM-DD and time as HH:MM."
                else:
                    if not _within_business_rules(local_dt):
                        reply_text = "That time isn't available. Please choose a weekday on the hour between 09:00 and 17:00."
                    else:
                        start_utc = local_dt.astimezone(UTC)
                        if _is_already_booked(conn, start_utc):
                            alts = _find_alternatives(conn, local_dt, tz_name, limit=2)
                            if alts:
                                a1 = alts[0].strftime("%Y-%m-%d %H:%M")
                                a2 = alts[1].strftime("%Y-%m-%d %H:%M") if len(alts) > 1 else None
                                if a2:
                                    reply_text = f"That slot is already booked. How about {a1} or {a2} ({tz_name})?"
                                else:
                                    reply_text = f"That slot is already booked. How about {a1} ({tz_name})?"
                            else:
                                reply_text = "That slot is already booked. Please suggest another time."
                        else:
                            service_type = merged_slots.get("service_type") or "general"
                            appointment_id = _create_appointment(conn, payload.user_id, start_utc, service_type)
                            reply_text = f"Booked your {service_type} appointment for {local_dt.strftime('%Y-%m-%d %H:%M')} ({tz_name})."
                            merged_slots["appointment_id"] = str(appointment_id)

        assistant_msg = {"role": "assistant", "content": reply_text, "ts": _utc_iso_now()}
        messages.append(assistant_msg)
        metadata["slots"] = merged_slots

        _save_session(conn, payload.session_id, messages, metadata)

        logger.info(
            "chat user_id=%s session_id=%s",
            str(payload.user_id),
            str(payload.session_id),
        )

        return ChatResponse(
            reply=reply_text,
            session_id=payload.session_id,
            appointment_id=appointment_id,
            extracted_slots=extracted or None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("chat_failed")
        raise HTTPException(status_code=500, detail="Internal Server Error") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
