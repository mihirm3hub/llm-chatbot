import uuid
from datetime import datetime

import psycopg2
from psycopg2.extras import Json

from .config import settings


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

    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_sessions (id, user_id, messages, metadata)
            VALUES (%s, %s, '[]'::jsonb, '{}'::jsonb)
            """,
            (str(session_id), str(user_id)),
        )
    connection.commit()
    return {"user_id": user_id, "messages": [], "metadata": {}}


def save_session(connection, session_id: uuid.UUID, messages: list, metadata: dict):
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE chat_sessions SET messages = %s, metadata = %s WHERE id = %s",
            (Json(messages), Json(metadata), str(session_id)),
        )
    connection.commit()


def create_appointment(connection, user_id: uuid.UUID, start_time_utc: datetime, end_time_utc: datetime, service_type: str) -> uuid.UUID:
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO appointments (user_id, start_time, end_time, service_type, status)
            VALUES (%s, %s, %s, %s, 'BOOKED')
            RETURNING id
            """,
            (str(user_id), start_time_utc, end_time_utc, service_type),
        )
        appointment_id = cur.fetchone()[0]
    connection.commit()
    return uuid.UUID(str(appointment_id))


def is_already_booked(connection, start_time_utc: datetime) -> bool:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM appointments
            WHERE start_time = %s AND status = 'BOOKED'
            LIMIT 1
            """,
            (start_time_utc,),
        )
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


def cancel_latest_booked_appointment(connection, user_id: uuid.UUID) -> uuid.UUID | None:
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
    connection.commit()
    if not row:
        return None
    return uuid.UUID(str(row[0]))
