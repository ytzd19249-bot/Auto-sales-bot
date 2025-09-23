from fastapi import FastAPI, Request, Depends
import requests
import os
from db import Base, engine, SessionLocal, get_db
from sqlalchemy.orm import Session

# Inicializamos tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

@app.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Respuesta básica (se puede mejorar después)
        response_text = f"Recibí tu mensaje: {text}"

        requests.post(WEBHOOK_URL, json={
            "chat_id": chat_id,
            "text": response_text
        })

    return {"ok": True}

@app.get("/")
def home():
    return {"status": "Bot de Ventas funcionando 🚀"}
