import crypto from "crypto";

export function requestId() {
	return (req, res, next) => {
		const existing = req.get("X-Request-Id");
		const id = existing && typeof existing === "string" ? existing : crypto.randomUUID();
		req.id = id;
		res.setHeader("X-Request-Id", id);
		next();
	};
}
