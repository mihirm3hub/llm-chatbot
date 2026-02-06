from fastapi import FastAPI
app = FastAPI()

@app.post('/chat')
def chat(payload: dict):
    return {"reply": "stub assistant reply", "session_id": payload.get("session_id")}
