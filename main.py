# main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests
import os

from db import SessionLocal, Producto, init_db

# Inicializar la base de datos
init_db()

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Render webhook URL

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


@app.get("/")
def home():
    return {"status": "Bot de Ventas corriendo 🚀"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return JSONResponse(content={"ok": True})

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    # Respuestas básicas
    if text.lower() in ["/start", "hola"]:
        send_message(chat_id, "👋 Bienvenido al *Bot de Ventas*.\nEscriba 'lista' para ver productos.")

    elif text.lower() == "lista":
        db = SessionLocal()
        productos = db.query(Producto).all()
        db.close()

        if productos:
            lista = "\n".join([f"🛒 {p.nombre} - ${p.precio}" for p in productos])
            send_message(chat_id, f"📋 Productos disponibles:\n{lista}")
        else:
            send_message(chat_id, "⚠️ No hay productos cargados en este momento.")

    else:
        send_message(chat_id, "❓ No entendí su mensaje. Use /start o escriba 'lista'.")

    return JSONResponse(content={"ok": True})


def send_message(chat_id, text):
    url = f"{BASE_TELEGRAM_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)
