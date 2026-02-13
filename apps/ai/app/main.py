import logging
import time
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .conversation import handle_chat

logger = logging.getLogger("ai")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Appointment Concierge AI")


class ChatRequest(BaseModel):
    user_id: uuid.UUID = Field(..., description="Authenticated user id")
    session_id: uuid.UUID = Field(..., description="Client-generated session id")
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    session_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    extracted_slots: dict | None = None
    persisted: bool = True


def _emit_persistence_alert(*, session_id: uuid.UUID, error: Exception) -> None:
    # Minimal metric/alert hook. Replace with real telemetry if available.
    logger.error(
        "metric=session_persist_failed session_id=%s error=%s",
        str(session_id),
        repr(error),
    )


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    if not settings.database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured")

    connection = None
    try:
        connection = db.conn()
        session = db.ensure_session(connection, payload.user_id, payload.session_id)

        reply, messages, metadata, appointment_id, extracted_slots = handle_chat(
            connection,
            user_id=payload.user_id,
            session_id=payload.session_id,
            message=payload.message,
            messages=session.get("messages") or [],
            metadata=session.get("metadata") or {},
        )

        # Persistence is best-effort by default: if saving fails, still return the successful reply.
        # Retries use exponential backoff to reduce load during transient failures.
        persisted = True
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                db.save_session(connection, payload.session_id, messages, metadata)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.exception(
                    "save_session_failed attempt=%s session_id=%s",
                    attempt + 1,
                    str(payload.session_id),
                )
                time.sleep(0.1 * (2**attempt))

        if last_exc is not None:
            persisted = False
            _emit_persistence_alert(session_id=payload.session_id, error=last_exc)
            if getattr(settings, "require_session_persistence", False):
                raise HTTPException(status_code=500, detail="Session persistence failed") from last_exc

        logger.info("chat user_id=%s session_id=%s", str(payload.user_id), str(payload.session_id))

        return ChatResponse(
            reply=reply,
            session_id=payload.session_id,
            appointment_id=appointment_id,
            extracted_slots=extracted_slots,
            persisted=persisted,
        )
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("chat_failed")
        raise HTTPException(status_code=500, detail="Internal Server Error") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
