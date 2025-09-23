import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from db import SessionLocal, Producto

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    with httpx.Client() as client:
        client.post(url, json=payload)

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text.startswith("/start"):
            send_message(chat_id, "🤖 Hola, soy tu Bot de Ventas. Estoy activo 🚀")
        else:
            db = SessionLocal()
            productos = db.query(Producto).all()
            db.close()
            if not productos:
                send_message(chat_id, "📭 No hay productos en este momento.")
            else:
                lista = "\n".join([f"🔹 {p.nombre} - ${p.precio}" for p in productos])
                send_message(chat_id, f"🛍️ Productos disponibles:\n{lista}")
    return JSONResponse(content={"ok": True})
