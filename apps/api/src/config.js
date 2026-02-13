export const PORT = Number(process.env.PORT || 3001);
export const DATABASE_URL = process.env.DATABASE_URL;
export const JWT_SECRET = process.env.JWT_SECRET;
export const AI_SERVICE_URL = process.env.AI_SERVICE_URL;

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
