import bcrypt from "bcryptjs";
import express from "express";
import { z } from "zod";

import { pool } from "../db.js";
import { asyncHandler } from "../lib/asyncHandler.js";
import { issueUserJwt } from "../middleware/auth.js";
import { validateBody } from "../middleware/validateBody.js";

const signupSchema = z.object({
	email: z.string().email().max(320),
	password: z.string().min(8).max(200),
});

const loginSchema = z.object({
	email: z.string().email().max(320),
	password: z.string().min(1).max(200),
});

function normalizeEmail(value) {
	return (value || "").trim().toLowerCase();
}

export const authRouter = express.Router();

authRouter.post(
	"/signup",
	validateBody(signupSchema),
	asyncHandler(async (req, res) => {
		const email = normalizeEmail(req.body?.email);
		const password = req.body?.password;
		const passwordHash = await bcrypt.hash(password, 10);

		try {
			const result = await pool.query(
				"INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id",
				[email, passwordHash]
			);
			const userId = result.rows[0]?.id;

			const token = issueUserJwt({ userId, email });
			return res.status(201).json({ jwt: token });
		} catch (err) {
			if (err?.code === "23505") {
				return res.status(409).json({ error: { message: "Email already in use" } });
			}
			throw err;
		}
	})
);

authRouter.post(
	"/login",
	validateBody(loginSchema),
	asyncHandler(async (req, res) => {
		const email = normalizeEmail(req.body?.email);
		const password = req.body?.password;
		const result = await pool.query("SELECT id, password_hash FROM users WHERE email = $1", [email]);
		const row = result.rows[0];
		if (!row) {
			return res.status(401).json({ error: { message: "Invalid credentials" } });
		}

		const ok = await bcrypt.compare(password, row.password_hash);
		if (!ok) {
			return res.status(401).json({ error: { message: "Invalid credentials" } });
		}

		const token = issueUserJwt({ userId: row.id, email });
		return res.json({ jwt: token });
	})
);
