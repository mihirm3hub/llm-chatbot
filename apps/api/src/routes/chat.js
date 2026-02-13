import express from "express";
import rateLimit from "express-rate-limit";
import { z } from "zod";

import { CHAT_TOKEN_EXPIRES_IN_SECONDS } from "../config.js";
import { asyncHandler } from "../lib/asyncHandler.js";
import { issueChatJwt, requireAuth, requireChatOrUserAuth } from "../middleware/auth.js";
import { validateBody } from "../middleware/validateBody.js";
import { callAiChat } from "../services/ai.js";

const chatbotTokenSchema = z.object({
	session_id: z.string().uuid(),
});

const chatSchema = z.object({
	session_id: z.string().uuid(),
	message: z.string().min(1).max(4000),
});

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

export const chatRouter = express.Router();

chatRouter.post(
	"/chatbot/token",
	requireAuth,
	chatTokenLimiter,
	validateBody(chatbotTokenSchema),
	asyncHandler(async (req, res) => {
		const { session_id } = req.body;
		const userId = req.user.id;
		const chatToken = issueChatJwt({ userId, sessionId: session_id });
		return res.json({ chat_token: chatToken, expires_in_seconds: CHAT_TOKEN_EXPIRES_IN_SECONDS });
	})
);

chatRouter.post(
	"/chat",
	chatLimiter,
	validateBody(chatSchema),
	requireChatOrUserAuth,
	asyncHandler(async (req, res) => {
		const { session_id, message } = req.body;
		const userId = req.user.id;

		try {
			const result = await callAiChat({
				userId,
				sessionId: session_id,
				message,
				requestId: req.id,
			});
			return res.json({ reply: result.reply, session_id: result.session_id });
		} catch (err) {
			console.error("ai_error", {
				requestId: req.id,
				code: err?.code,
				status: err?.status,
			});
			return res.status(502).json({ error: { message: "AI service unavailable" } });
		}
	})
);
