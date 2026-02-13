import { AI_SERVICE_URL } from "../config.js";

const SENSITIVE_KEY_RE = /pass(word)?|secret|token|api[_-]?key|authorization|cookie|set-cookie|session|jwt|bearer/i;

function sanitizeString(value) {
	if (typeof value !== "string") return value;

	let sanitized = value;
	// Redact common credential/token patterns that might appear in error bodies.
	sanitized = sanitized.replace(/Bearer\s+[^\s\"]+/gi, "Bearer [REDACTED]");
	sanitized = sanitized.replace(/\bsk-[A-Za-z0-9]{20,}\b/g, "sk-[REDACTED]");
	sanitized = sanitized.replace(
		/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
		"[REDACTED_JWT]",
	);

	const maxLen = 2000;
	if (sanitized.length > maxLen) {
		sanitized = `${sanitized.slice(0, maxLen)}…[truncated]`;
	}

	return sanitized;
}

function sanitizeObject(value, depth = 0) {
	if (value == null) return value;
	if (depth > 4) return "[truncated]";

	if (Array.isArray(value)) {
		const maxItems = 50;
		const items = value.slice(0, maxItems).map((item) => sanitizeObject(item, depth + 1));
		if (value.length > maxItems) items.push("…[truncated]");
		return items;
	}

	if (typeof value !== "object") {
		return typeof value === "string" ? sanitizeString(value) : value;
	}

	const maxEntries = 50;
	const out = {};
	let count = 0;
	for (const [key, val] of Object.entries(value)) {
		count += 1;
		if (count > maxEntries) {
			out._truncated = true;
			break;
		}

		if (SENSITIVE_KEY_RE.test(key)) {
			out[key] = "[REDACTED]";
			continue;
		}

		out[key] = sanitizeObject(val, depth + 1);
	}

	return out;
}

function sanitizeErrorBody(body) {
	if (body == null) return null;
	if (typeof body === "string") return sanitizeString(body);
	if (typeof body === "object") return sanitizeObject(body);
	return sanitizeString(String(body));
}

export async function callAiChat({ userId, sessionId, message, requestId }) {
	const url = new URL("/chat", AI_SERVICE_URL).toString();
	const controller = new AbortController();
	const timeoutMs = 25_000;
	const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

	try {
		const resp = await fetch(url, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				...(requestId ? { "X-Request-Id": requestId } : null),
			},
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
			const err = new Error("AI service error");
			err.code = "AI_BAD_STATUS";
			err.status = resp.status;
			// `err.body` is sanitized/redacted and is safe to log.
			err.body = sanitizeErrorBody(data ?? text);
			// Keep raw payload for debugging only; avoid logging/serializing this field.
			Object.defineProperty(err, "_rawBody", {
				value: data ?? text,
				enumerable: false,
			});
			throw err;
		}

		if (!data || typeof data.reply !== "string") {
			const err = new Error("Invalid AI response");
			err.code = "AI_BAD_RESPONSE";
			// `err.body` is sanitized/redacted and is safe to log.
			err.body = sanitizeErrorBody(data ?? text);
			Object.defineProperty(err, "_rawBody", {
				value: data ?? text,
				enumerable: false,
			});
			throw err;
		}

		return { reply: data.reply, session_id: data.session_id ?? sessionId };
	} catch (err) {
		if (err?.name === "AbortError") {
			const timeoutErr = new Error("AI service timeout");
			timeoutErr.code = "AI_TIMEOUT";
			throw timeoutErr;
		}
		throw err;
	} finally {
		clearTimeout(timeoutId);
	}
}
