import { z } from "zod";

// eslint-disable-next-line no-unused-vars
export function errorHandler(err, req, res, next) {
	if (err instanceof z.ZodError) {
		return res.status(400).json({
			error: {
				message: "Invalid request body",
				details: err.issues.map((i) => ({ path: i.path, message: i.message })),
			},
		});
	}

	console.error(err);
	return res.status(500).json({ error: { message: "Internal Server Error" } });
}
