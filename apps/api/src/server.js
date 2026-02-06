import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import rateLimit from 'express-rate-limit';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { Pool } from 'pg';
import { z } from 'zod';

const PORT = Number(process.env.PORT || 3001);
const DATABASE_URL = process.env.DATABASE_URL;
const JWT_SECRET = process.env.JWT_SECRET;

if (!DATABASE_URL) {
	throw new Error('Missing DATABASE_URL');
}
if (!JWT_SECRET) {
	throw new Error('Missing JWT_SECRET');
}

const pool = new Pool({ connectionString: DATABASE_URL });

const app = express();
app.set('trust proxy', 1);

app.use(express.json({ limit: '1mb' }));
app.use(
	cors({
		origin: 'http://localhost:3000',
		credentials: true,
	})
);
app.use(morgan('tiny'));

function asyncHandler(fn) {
	return (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
}

function validateBody(schema) {
	return (req, res, next) => {
		const result = schema.safeParse(req.body);
		if (!result.success) {
			return next(result.error);
		}
		req.body = result.data;
		next();
	};
}

function issueJwt(payload, expiresIn) {
	return jwt.sign(payload, JWT_SECRET, { expiresIn });
}

function requireAuth(req, res, next) {
	const header = req.headers.authorization;
	const token = header?.startsWith('Bearer ') ? header.slice('Bearer '.length) : null;
	if (!token) {
		return res.status(401).json({ error: { message: 'Missing Authorization header' } });
	}

	try {
		const decoded = jwt.verify(token, JWT_SECRET);
		if (!decoded || typeof decoded !== 'object') {
			return res.status(401).json({ error: { message: 'Invalid token' } });
		}
		if (decoded.scope && decoded.scope !== 'user') {
			return res.status(401).json({ error: { message: 'Invalid token scope' } });
		}
		req.user = { id: decoded.sub, email: decoded.email };
		if (!req.user.id) {
			return res.status(401).json({ error: { message: 'Invalid token subject' } });
		}
		next();
	} catch {
		return res.status(401).json({ error: { message: 'Invalid token' } });
	}
}

const signupSchema = z.object({
	email: z.string().email().max(320),
	password: z.string().min(8).max(200),
});

const loginSchema = z.object({
	email: z.string().email().max(320),
	password: z.string().min(1).max(200),
});

const chatbotTokenSchema = z.object({
	session_id: z.string().uuid(),
});

const chatSchema = z.object({
	session_id: z.string().uuid(),
	message: z.string().min(1).max(4000),
});

async function callAiChat({ userId, sessionId, message }) {
	const baseUrl = process.env.AI_SERVICE_URL;
	if (!baseUrl) {
		const err = new Error('Missing AI_SERVICE_URL');
		err.code = 'AI_CONFIG';
		throw err;
	}

	const url = new URL('/chat', baseUrl).toString();
	const controller = new AbortController();
	const timeoutMs = 10_000;
	const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

	try {
		const resp = await fetch(url, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_id: userId, session_id: sessionId, message }),
			signal: controller.signal,
		});

		const text = await resp.text();
		let data;
		try {
			data = text ? JSON.parse(text) : null;
		} catch {
			data = null;
		}

		if (!resp.ok) {
			const err = new Error('AI service error');
			err.code = 'AI_BAD_STATUS';
			err.status = resp.status;
			err.body = data ?? text;
			throw err;
		}

		if (!data || typeof data.reply !== 'string') {
			const err = new Error('Invalid AI response');
			err.code = 'AI_BAD_RESPONSE';
			err.body = data ?? text;
			throw err;
		}

		return { reply: data.reply, session_id: data.session_id ?? sessionId };
	} catch (err) {
		if (err?.name === 'AbortError') {
			const timeoutErr = new Error('AI service timeout');
			timeoutErr.code = 'AI_TIMEOUT';
			throw timeoutErr;
		}
		throw err;
	} finally {
		clearTimeout(timeoutId);
	}
}

app.get('/health', (req, res) => res.json({ ok: true }));

app.post(
	'/api/auth/signup',
	validateBody(signupSchema),
	asyncHandler(async (req, res) => {
		const { email, password } = req.body;
		const passwordHash = await bcrypt.hash(password, 10);

		try {
			const result = await pool.query(
				'INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id',
				[email, passwordHash]
			);
			const userId = result.rows[0]?.id;

			const token = issueJwt({ sub: userId, email, scope: 'user' }, '7d');
			return res.status(201).json({ jwt: token });
		} catch (err) {
			if (err?.code === '23505') {
				return res.status(409).json({ error: { message: 'Email already in use' } });
			}
			throw err;
		}
	})
);

app.post(
	'/api/auth/login',
	validateBody(loginSchema),
	asyncHandler(async (req, res) => {
		const { email, password } = req.body;
		const result = await pool.query('SELECT id, password_hash FROM users WHERE email = $1', [email]);
		const row = result.rows[0];
		if (!row) {
			return res.status(401).json({ error: { message: 'Invalid credentials' } });
		}

		const ok = await bcrypt.compare(password, row.password_hash);
		if (!ok) {
			return res.status(401).json({ error: { message: 'Invalid credentials' } });
		}

		const token = issueJwt({ sub: row.id, email, scope: 'user' }, '7d');
		return res.json({ jwt: token });
	})
);

const chatTokenLimiter = rateLimit({
	windowMs: 60 * 1000,
	max: 30,
	standardHeaders: true,
	legacyHeaders: false,
});

const chatLimiter = rateLimit({
	windowMs: 60 * 1000,
	max: 60,
	standardHeaders: true,
	legacyHeaders: false,
});

app.post(
	'/api/chatbot/token',
	requireAuth,
	chatTokenLimiter,
	validateBody(chatbotTokenSchema),
	asyncHandler(async (req, res) => {
		const { session_id } = req.body;
		const userId = req.user.id;
		const expiresInSeconds = 300;
		const chatToken = issueJwt(
			{ scope: 'chat', user_id: userId, session_id },
			`${expiresInSeconds}s`
		);
		return res.json({ chat_token: chatToken, expires_in_seconds: expiresInSeconds });
	})
);

app.post(
	'/api/chat',
	requireAuth,
	chatLimiter,
	validateBody(chatSchema),
	asyncHandler(async (req, res) => {
		const { session_id, message } = req.body;
		const userId = req.user.id;

		try {
			const result = await callAiChat({ userId, sessionId: session_id, message });
			return res.json({ reply: result.reply, session_id: result.session_id });
		} catch (err) {
			console.error('ai_error', {
				code: err?.code,
				status: err?.status,
			});
			return res.status(502).json({ error: { message: 'AI service unavailable' } });
		}
	})
);

// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
	if (err instanceof z.ZodError) {
		return res.status(400).json({
			error: {
				message: 'Invalid request body',
				details: err.issues.map((i) => ({ path: i.path, message: i.message })),
			},
		});
	}

	console.error(err);
	return res.status(500).json({ error: { message: 'Internal Server Error' } });
});

app.listen(PORT, () => console.log(`API on ${PORT}`));
