import logging
import uuid
from datetime import UTC, datetime, timedelta

from . import booking, db
from .config import settings
from .langchain_chains import compose_reply, extract_slots
from .langchain_runtime import llm_enabled

logger = logging.getLogger("ai")


def _deterministic_general_chat_reply(message: str) -> str:
    msg = (message or "").strip().lower()

    if any(w in msg for w in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]):
        return "Hi! I can help you book or reschedule an appointment. What date and time would you like?"

    if "space" in msg and ("fact" in msg or "fun" in msg):
        return (
            "Fun space fact: a day on Venus is longer than a year on Venus. "
            "If you'd like to book an appointment, tell me the date and time you prefer."
        )

    if any(w in msg for w in ["thank", "thanks"]):
        return "You’re welcome. If you want to book an appointment, what date and time works for you?"

    return "I can help with appointment bookings. What date and time would you like?"


def _utc_iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _get_slots(metadata: dict) -> dict:
    slots = metadata.get("slots")
    return slots if isinstance(slots, dict) else {}


def _set_slots(metadata: dict, slots: dict) -> dict:
    metadata = dict(metadata or {})
    metadata["slots"] = slots
    return metadata


def _infer_intent(message: str) -> str:
    msg = (message or "").strip().lower()
    if any(w in msg for w in ["reschedule", "move", "change time", "change the time", "different time"]):
        return "reschedule"
    if any(w in msg for w in ["book", "schedule", "appointment", "meeting", "reserve"]):
        return "booking"
    return "inquiry"


def _is_cancel(message: str) -> bool:
    msg = (message or "").strip().lower()
    return any(p in msg for p in ["cancel", "never mind", "nevermind", "forget it", "stop"])


def _is_view_booking(message: str) -> bool:
    msg = (message or "").strip().lower()
    return any(
        p in msg for p in ["what did i book", "what have i booked", "my booking", "my appointment"]
    ) or ("what" in msg and "book" in msg)


def _is_reschedule(message: str) -> bool:
    msg = (message or "").strip().lower()
    return any(p in msg for p in ["reschedule", "move", "change time", "change the time", "different time"])


def _get_state(metadata: dict) -> str | None:
    state = (metadata or {}).get("state")
    return state if isinstance(state, str) else None


def _set_state(metadata: dict, state: str | None) -> dict:
    metadata = dict(metadata or {})
    if state is None:
        metadata.pop("state", None)
    else:
        metadata["state"] = state
    return metadata


def _fallback_service_type(message: str) -> str | None:
    msg = (message or "").strip().lower()
    for candidate in ["consultation", "demo", "intro", "introduction", "call", "meeting", "check-in", "sync"]:
        if candidate in msg:
            return "consultation" if candidate in {"intro", "introduction", "check-in", "sync"} else candidate
    return None


def _llm_extract_slots(message: str, existing_slots: dict) -> dict:
    if not llm_enabled():
        logger.info("slot_extract mode=deterministic provider=%s", settings.llm_provider)
        return {}

    try:
        extracted = extract_slots(message=message, existing_slots=existing_slots or {})
        logger.info("slot_extract mode=llm provider=%s", settings.llm_provider)
        return extracted
    except Exception as exc:
        # Best-effort only; deterministic parsing still works without LLM extraction.
        logger.warning(
            "slot_extract mode=llm_failed provider=%s error=%s",
            settings.llm_provider,
            repr(exc),
        )
        return {}


def _llm_compose_reply(*, history: list, action: str, context: dict, fallback: str) -> str:
    if not llm_enabled():
        logger.info("reply_compose mode=deterministic provider=%s action=%s", settings.llm_provider, action)
        return fallback

    try:
        text = compose_reply(history=history, action=action, context=context)
        if text:
            logger.info("reply_compose mode=llm provider=%s action=%s", settings.llm_provider, action)
            return text

        logger.info("reply_compose mode=llm_empty provider=%s action=%s", settings.llm_provider, action)
        return fallback
    except Exception as exc:
        logger.warning(
            "reply_compose mode=llm_failed provider=%s action=%s error=%s",
            settings.llm_provider,
            action,
            repr(exc),
        )
        return fallback


def handle_chat(
    connection,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    message: str,
    messages: list,
    metadata: dict,
) -> tuple[str, list, dict, uuid.UUID | None, dict | None]:
    now_utc = datetime.now(tz=UTC)

    prior_slots = _get_slots(metadata)
    prior_state = _get_state(metadata)

    deterministic = {
        "date": booking.parse_date(message, now_utc),
        "time": booking.parse_time(message),
        "timezone": booking.parse_timezone(message),
        "service_type": _fallback_service_type(message),
    }
    llm_slots = _llm_extract_slots(message, prior_slots)

    provided_date = bool(deterministic.get("date") or (llm_slots or {}).get("date"))
    provided_time = bool(deterministic.get("time") or (llm_slots or {}).get("time"))
    provided_timezone = bool(deterministic.get("timezone") or (llm_slots or {}).get("timezone"))

    # Merge precedence: start from prior, add LLM/fallback, then deterministic overwrites.
    merged = booking.merge_slots(prior_slots, llm_slots)
    merged = booking.merge_slots(merged, deterministic)

    if _is_cancel(message):
        merged.pop("intent", None)
        merged.pop("date", None)
        merged.pop("time", None)
        merged.pop("timezone", None)
        merged.pop("service_type", None)
        merged.pop("appointment_id", None)
        prior_state = None

    merged.setdefault("service_type", "general")

    # Prefer explicit reschedule keywording.
    heuristic_intent = _infer_intent(message)
    if _is_reschedule(message):
        merged["intent"] = "reschedule"
    else:
        # If we're in the middle of a booking, don't let LLM intent flip us back to inquiry.
        if (
            (prior_slots.get("intent") == "booking" or prior_state == "COLLECTING")
            and merged.get("intent") in {None, "inquiry"}
        ):
            merged["intent"] = "booking"

        # If user clearly asks to book, override any LLM misclassification.
        if heuristic_intent == "booking":
            merged["intent"] = "booking"
        elif not merged.get("intent"):
            merged["intent"] = heuristic_intent

    # Timezone is optional. If it's invalid, we simply ignore it and treat times as UTC.
    if merged.get("timezone") and not booking.is_valid_timezone(str(merged.get("timezone"))):
        merged.pop("timezone", None)

    # Persist message log
    out_messages = list(messages or [])
    out_messages.append({"role": "user", "content": message, "ts": _utc_iso_now()})

    appointment_id: uuid.UUID | None = None
    extracted_slots = dict(merged)

    # If we already booked an appointment in this session, avoid looping.
    if prior_state == "BOOKED" and merged.get("intent") not in {"reschedule", "booking"} and not _is_view_booking(message):
        fallback = "Your appointment is already booked for this session. If you want to reschedule, tell me the new time (and timezone if different)."
        reply = _llm_compose_reply(
            history=out_messages,
            action="booked",
            context={"already_booked": True},
            fallback=fallback,
        )
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, "BOOKED")
        return reply, out_messages, out_metadata, None, extracted_slots

    if _is_view_booking(message):
        latest = db.fetch_latest_booked_appointment(connection, user_id)
        if not latest:
            fallback = "You don't have any booked appointments yet. If you'd like to book one, tell me the day, time, and timezone."
            reply = _llm_compose_reply(
                history=out_messages,
                action="view_booking",
                context={"has_booking": False},
                fallback=fallback,
            )
        else:
            start_time = latest["start_time"].astimezone(UTC)
            fallback = f"Your latest appointment is booked for {start_time.strftime('%Y-%m-%d %H:%M')} UTC (type: {latest['service_type']})."
            reply = _llm_compose_reply(
                history=out_messages,
                action="view_booking",
                context={
                    "has_booking": True,
                    "start_time_utc": start_time.strftime("%Y-%m-%d %H:%M"),
                    "service_type": latest["service_type"],
                },
                fallback=fallback,
            )
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        return reply, out_messages, out_metadata, None, extracted_slots

    if _is_cancel(message):
        fallback = "Okay — cancelled. If you want to book, tell me the date, time, and timezone."
        reply = _llm_compose_reply(history=out_messages, action="cancelled", context={}, fallback=fallback)
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, None)
        return reply, out_messages, out_metadata, None, extracted_slots

    reschedule_mode = merged.get("intent") == "reschedule"
    if reschedule_mode:
        # Rescheduling: reuse existing date/timezone if present, but if the new message doesn't
        # include a time/timezone, force asking for those.
        merged.pop("appointment_id", None)
        prior_state = None
        if not provided_time:
            merged.pop("time", None)
        if not provided_timezone:
            merged.pop("timezone", None)

        # Continue the normal booking slot-filling flow.
        merged["intent"] = "booking"

    if merged.get("intent") != "booking":
        fallback = _deterministic_general_chat_reply(message)
        reply = _llm_compose_reply(
            history=out_messages,
            action="general_chat",
            context={
                "user_message": message,
                "capabilities": ["book", "reschedule", "cancel", "view_booking"],
                "note": "If user message is unrelated, answer briefly then ask what date/time they'd like to book.",
            },
            fallback=fallback,
        )
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, prior_state)
        return reply, out_messages, out_metadata, None, extracted_slots

    if not merged.get("date"):
        fallback = "What date would you like to book? (e.g. 2026-02-24 or 'next Tuesday')"
        reply = _llm_compose_reply(history=out_messages, action="ask_date", context={}, fallback=fallback)
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, "COLLECTING")
        return reply, out_messages, out_metadata, None, extracted_slots

    if not merged.get("time"):
        fallback = "What time works for you? (e.g. 3pm or 15:00)"
        reply = _llm_compose_reply(history=out_messages, action="ask_time", context={}, fallback=fallback)
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, "COLLECTING")
        return reply, out_messages, out_metadata, None, extracted_slots

    try:
        local_dt, tz_name = booking.parse_local_start(merged)
    except Exception:
        fallback = "I couldn't parse that date/time. Please share date + time again (e.g. 2026-02-24 15:00 America/New_York)."
        reply = _llm_compose_reply(history=out_messages, action="invalid_datetime", context={}, fallback=fallback)
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, "COLLECTING")
        return reply, out_messages, out_metadata, None, extracted_slots

    start_utc = local_dt.astimezone(UTC)

    if not booking.within_business_rules(start_utc):
        fallback = "That time isn't available. Please choose a weekday, on the hour, between 09:00 and 17:00 UTC."
        reply = _llm_compose_reply(history=out_messages, action="outside_rules", context={}, fallback=fallback)
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, "COLLECTING")
        return reply, out_messages, out_metadata, None, extracted_slots

    if db.is_already_booked(connection, start_utc):
        alternatives = booking.find_alternatives(
            lambda dt_utc: db.is_already_booked(connection, dt_utc),
            start_utc,
            tz_name,
            limit=2,
        )
        if alternatives:
            formatted = " or ".join([d.strftime("%Y-%m-%d %H:%M") for d in alternatives])
            fallback = f"That slot is already booked. How about {formatted} ({tz_name})?"
            reply = _llm_compose_reply(
                history=out_messages,
                action="conflict",
                context={"timezone": tz_name, "alternatives": [d.strftime("%Y-%m-%d %H:%M") for d in alternatives]},
                fallback=fallback,
            )
        else:
            fallback = "That slot is already booked. Please suggest another time."
            reply = _llm_compose_reply(
                history=out_messages,
                action="conflict",
                context={"timezone": tz_name, "alternatives": []},
                fallback=fallback,
            )
        out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
        out_metadata = _set_slots(metadata, merged)
        out_metadata = _set_state(out_metadata, "COLLECTING")
        return reply, out_messages, out_metadata, None, extracted_slots

    end_utc = start_utc + timedelta(hours=1)
    service_type = (merged.get("service_type") or "general").strip() or "general"

    # If rescheduling, cancel the latest booked appointment first (best-effort).
    if reschedule_mode:
        db.cancel_latest_booked_appointment(connection, user_id)

    appointment_id = db.create_appointment(connection, user_id, start_utc, end_utc, service_type)
    merged["appointment_id"] = str(appointment_id)

    fallback = f"Booked — {local_dt.strftime('%Y-%m-%d %H:%M')} {tz_name} (type: {service_type})."
    reply = _llm_compose_reply(
        history=out_messages,
        action="booked",
        context={
            "local_start": local_dt.strftime("%Y-%m-%d %H:%M"),
            "timezone": tz_name,
            "service_type": service_type,
        },
        fallback=fallback,
    )
    out_messages.append({"role": "assistant", "content": reply, "ts": _utc_iso_now()})
    out_metadata = _set_slots(metadata, merged)
    out_metadata = _set_state(out_metadata, "BOOKED")
    extracted_slots = dict(merged)
    return reply, out_messages, out_metadata, appointment_id, extracted_slots
