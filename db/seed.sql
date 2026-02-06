WITH demo_user AS (
	INSERT INTO users (email, password_hash)
	VALUES ('demo@example.com', '$2b$10$demo_seed_hash_not_for_production')
	ON CONFLICT (email) DO UPDATE
		SET password_hash = users.password_hash
	RETURNING id
),
session_row AS (
	INSERT INTO chat_sessions (user_id, messages, metadata)
	SELECT
		id,
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
	FROM demo_user
	RETURNING id, user_id
)
INSERT INTO appointments (user_id, start_time, end_time, service_type, status)
SELECT
	user_id,
	'2026-02-10T15:00:00Z'::timestamptz,
	'2026-02-10T15:30:00Z'::timestamptz,
	'general',
	'BOOKED'
FROM session_row
ON CONFLICT DO NOTHING;
