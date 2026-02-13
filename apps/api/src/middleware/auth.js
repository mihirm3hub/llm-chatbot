import jwt from "jsonwebtoken";

import { CHAT_TOKEN_EXPIRES_IN_SECONDS, JWT_EXPIRES_IN, JWT_SECRET } from "../config.js";

export function issueUserJwt({ userId, email }) {
	return jwt.sign({ sub: userId, email, scope: "user" }, JWT_SECRET, { expiresIn: JWT_EXPIRES_IN });
}

export function issueChatJwt({ userId, sessionId }) {
	return jwt.sign(
		{ scope: "chat", user_id: userId, session_id: sessionId },
		JWT_SECRET,
		{ expiresIn: `${CHAT_TOKEN_EXPIRES_IN_SECONDS}s` }
	);
}

export function requireAuth(req, res, next) {
	const header = req.headers.authorization;
	const token = header?.startsWith("Bearer ") ? header.slice("Bearer ".length) : null;
	if (!token) {
		return res.status(401).json({ error: { message: "Missing Authorization header" } });
	}

	try {
		const decoded = jwt.verify(token, JWT_SECRET);
		if (!decoded || typeof decoded !== "object") {
			return res.status(401).json({ error: { message: "Invalid token" } });
		}
		if (decoded.scope && decoded.scope !== "user") {
			return res.status(401).json({ error: { message: "Invalid token scope" } });
		}
		req.user = { id: decoded.sub, email: decoded.email };
		if (!req.user.id) {
			return res.status(401).json({ error: { message: "Invalid token subject" } });
		}
		next();
	} catch {
		return res.status(401).json({ error: { message: "Invalid token" } });
	}
}

export function requireChatOrUserAuth(req, res, next) {
	const header = req.headers.authorization;
	const token = header?.startsWith("Bearer ") ? header.slice("Bearer ".length) : null;
	if (!token) {
		return res.status(401).json({ error: { message: "Missing Authorization header" } });
	}

	try {
		const decoded = jwt.verify(token, JWT_SECRET);
		if (!decoded || typeof decoded !== "object") {
			return res.status(401).json({ error: { message: "Invalid token" } });
		}

		if (decoded.scope === "chat") {
			const tokenSessionId = decoded.session_id;
			const tokenUserId = decoded.user_id;
			if (!tokenSessionId || !tokenUserId) {
				return res.status(401).json({ error: { message: "Invalid token" } });
			}
			if (tokenSessionId !== req.body.session_id) {
				return res.status(401).json({ error: { message: "Invalid token session" } });
			}
			req.user = { id: tokenUserId };
			return next();
		}

		if (decoded.scope && decoded.scope !== "user") {
			return res.status(401).json({ error: { message: "Invalid token scope" } });
		}
		req.user = { id: decoded.sub, email: decoded.email };
		if (!req.user.id) {
			return res.status(401).json({ error: { message: "Invalid token subject" } });
		}
		return next();
	} catch {
		return res.status(401).json({ error: { message: "Invalid token" } });
	}
}
