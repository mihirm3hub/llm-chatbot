CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS appointments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  service_type TEXT NOT NULL DEFAULT 'general',
  status TEXT NOT NULL DEFAULT 'BOOKED',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT appointments_status_chk CHECK (status IN ('BOOKED', 'CANCELLED'))
);

CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  messages JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_appt_user_time ON appointments(user_id, start_time);
CREATE INDEX IF NOT EXISTS idx_appt_start_time ON appointments(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id_id ON chat_sessions(user_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_metadata_gin ON chat_sessions USING GIN (metadata);

CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chat_sessions_set_updated_at ON chat_sessions;
CREATE TRIGGER trg_chat_sessions_set_updated_at
BEFORE UPDATE ON chat_sessions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();
