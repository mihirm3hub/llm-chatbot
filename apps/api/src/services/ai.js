import { AI_SERVICE_URL } from "../config.js";

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
			err.body = data ?? text;
			throw err;
		}

		if (!data || typeof data.reply !== "string") {
			const err = new Error("Invalid AI response");
			err.code = "AI_BAD_RESPONSE";
			err.body = data ?? text;
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
