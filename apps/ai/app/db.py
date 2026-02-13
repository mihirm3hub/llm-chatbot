import uuid
from datetime import datetime

import psycopg2
from psycopg2.extras import Json

from .config import settings


class SessionNotFoundError(RuntimeError):
    pass


class AlreadyBookedError(RuntimeError):
    pass


def conn():
    if not settings.database_url:
        raise RuntimeError("Missing DATABASE_URL")
    return psycopg2.connect(settings.database_url)


def load_session(connection, session_id: uuid.UUID):
    with connection.cursor() as cur:
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


def ensure_session(connection, user_id: uuid.UUID, session_id: uuid.UUID):
    existing = load_session(connection, session_id)
    if existing:
        if existing["user_id"] != user_id:
            raise PermissionError("Session does not belong to user")
        return existing

    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE id = %s", (str(user_id),))
        if cur.fetchone() is None:
            raise ValueError("Unknown user_id")

    # Atomic upsert to avoid races if multiple requests try to create the same session_id.
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_sessions (id, user_id, messages, metadata)
            VALUES (%s, %s, '[]'::jsonb, '{}'::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            (str(session_id), str(user_id)),
        )
    connection.commit()

    session = load_session(connection, session_id)
    if not session:
        raise RuntimeError(f"Failed to ensure chat session: {session_id}")
    if session["user_id"] != user_id:
        raise PermissionError("Session does not belong to user")
    return session


def save_session(connection, session_id: uuid.UUID, messages: list, metadata: dict):
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE chat_sessions SET messages = %s, metadata = %s WHERE id = %s",
            (Json(messages), Json(metadata), str(session_id)),
        )

        if cur.rowcount == 0:
            raise SessionNotFoundError(f"Chat session not found for id={session_id}")
    connection.commit()


def create_appointment(
    connection,
    user_id: uuid.UUID,
    start_time_utc: datetime,
    end_time_utc: datetime,
    service_type: str,
    *,
    commit: bool = True,
) -> uuid.UUID:
    with connection.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO appointments (user_id, start_time, end_time, service_type, status)
                VALUES (%s, %s, %s, %s, 'BOOKED')
                RETURNING id
                """,
                (str(user_id), start_time_utc, end_time_utc, service_type),
            )
            appointment_id = cur.fetchone()[0]
        except psycopg2.IntegrityError as exc:
            # Most commonly a unique constraint/index violation for an already-booked slot.
            if getattr(exc, "pgcode", None) == "23505":
                raise AlreadyBookedError("Appointment slot already booked") from exc
            raise
    if commit:
        connection.commit()
    return uuid.UUID(str(appointment_id))


def is_already_booked(connection, start_time_utc: datetime, end_time_utc: datetime, *, lock: bool = False) -> bool:
    with connection.cursor() as cur:
        query = """
        SELECT id
        FROM appointments
        WHERE status = 'BOOKED'
          AND start_time < %s
          AND COALESCE(end_time, start_time + interval '1 hour') > %s
        LIMIT 1
        """
        if lock:
            query += " FOR UPDATE"

        cur.execute(query, (end_time_utc, start_time_utc))
        return cur.fetchone() is not None


def fetch_latest_booked_appointment(connection, user_id: uuid.UUID):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT start_time, service_type
            FROM appointments
            WHERE user_id = %s AND status = 'BOOKED'
            ORDER BY start_time DESC
            LIMIT 1
            """,
            (str(user_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        start_time, service_type = row
        return {"start_time": start_time, "service_type": service_type}


def cancel_latest_booked_appointment(connection, user_id: uuid.UUID, *, commit: bool = True) -> uuid.UUID | None:
    """Mark the latest BOOKED appointment as CANCELLED (best-effort)."""

    with connection.cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT id
                FROM appointments
                WHERE user_id = %s AND status = 'BOOKED'
                ORDER BY start_time DESC
                LIMIT 1
            )
            UPDATE appointments
            SET status = 'CANCELLED'
            WHERE id IN (SELECT id FROM latest)
            RETURNING id
            """,
            (str(user_id),),
        )
        row = cur.fetchone()
    if commit:
        connection.commit()
    if not row:
        return None
    return uuid.UUID(str(row[0]))
