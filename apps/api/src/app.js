import cors from "cors";
import express from "express";
import morgan from "morgan";

import { CORS_ORIGIN } from "./config.js";

import { authRouter } from "./routes/auth.js";
import { chatRouter } from "./routes/chat.js";
import { errorHandler } from "./middleware/errorHandler.js";
import { requestId } from "./middleware/requestId.js";

export function createApp() {
	const app = express();
	app.set("trust proxy", 1);

	app.use(requestId());
	app.use(express.json({ limit: "1mb" }));
	app.use(
		cors({
			origin: CORS_ORIGIN,
			credentials: true,
			allowedHeaders: ["Content-Type", "Authorization", "X-Request-Id"],
			methods: ["GET", "POST", "OPTIONS"],
		})
	);

	morgan.token("id", (req) => req.id);
	app.use(morgan(":id :method :url :status :response-time ms"));

	app.get("/health", (req, res) => res.json({ ok: true }));

	app.use("/api/auth", authRouter);
	app.use("/api", chatRouter);

	app.use(errorHandler);
	return app;
}
