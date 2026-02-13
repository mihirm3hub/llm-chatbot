const rawPort = process.env.PORT;
const parsedPort = rawPort ? Number.parseInt(rawPort, 10) : 3001;
if (!Number.isInteger(parsedPort) || parsedPort <= 0 || parsedPort > 65535) {
	console.warn(`Invalid PORT value '${rawPort}', falling back to 3001`);
}

export const PORT = (!Number.isInteger(parsedPort) || parsedPort <= 0 || parsedPort > 65535) ? 3001 : parsedPort;
export const DATABASE_URL = process.env.DATABASE_URL;
export const JWT_SECRET = process.env.JWT_SECRET;
export const AI_SERVICE_URL = process.env.AI_SERVICE_URL;
export const CORS_ORIGIN = process.env.CORS_ORIGIN || "http://localhost:3000";

if (!DATABASE_URL) {
	throw new Error("Missing DATABASE_URL");
}
if (!JWT_SECRET) {
	throw new Error("Missing JWT_SECRET");
}
if (!AI_SERVICE_URL) {
	throw new Error("Missing AI_SERVICE_URL");
}

export const JWT_EXPIRES_IN = "7d";
export const CHAT_TOKEN_EXPIRES_IN_SECONDS = 300;
