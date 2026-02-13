-- Seed data is intentionally minimal and idempotent.
-- Password hash is a placeholder and NOT a real bcrypt hash.

INSERT INTO users (email, password_hash)
VALUES ('demo@example.com', '$2b$10$demo_seed_hash_not_for_production')
ON CONFLICT (email) DO NOTHING;

INSERT INTO chat_sessions (id, user_id, messages, metadata)
SELECT
	'00000000-0000-0000-0000-000000000001'::uuid,
	u.id,
	(
		'[
			{"role":"user","content":"Hi, I want to book an appointment next Tuesday at 3pm","ts":"2026-02-06T10:00:00Z"},
			{"role":"assistant","content":"Sure — what timezone should I use?","ts":"2026-02-06T10:00:02Z"}
		]'::jsonb
	),
	(
		'{
			"slots": {
				"intent": "booking",
				"date": "2026-02-10",
				"time": "15:00",
				"timezone": null,
				"service_type": "general"
			}
		}'::jsonb
	)
FROM users u
WHERE u.email = 'demo@example.com'
ON CONFLICT (id) DO NOTHING;

INSERT INTO appointments (id, user_id, start_time, end_time, service_type, status)
SELECT
	'00000000-0000-0000-0000-000000000002'::uuid,
	u.id,
	'2026-02-10T15:00:00Z'::timestamptz,
	'2026-02-10T16:00:00Z'::timestamptz,
	'general',
	'BOOKED'
FROM users u
WHERE u.email = 'demo@example.com'
ON CONFLICT (id) DO NOTHING;
