# main.py
import os
import httpx
from fastapi import FastAPI, Request
from db import SessionLocal, Producto, init_db
from sqlalchemy.orm import Session
import openai

# Inicializar FastAPI
app = FastAPI()

# Inicializar DB
init_db()

# Cargar variables de entorno
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_KEY


# Enviar mensaje a Telegram
async def send_message(chat_id: int, text: str):
    url = f"{BASE_URL}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})


# Procesar mensaje del usuario
async def process_message(chat_id: int, text: str, db: Session):
    text_lower = text.lower()

    # 1. Revisar si pide productos
    producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{text_lower}%")).first()
    if producto:
        respuesta = f"📦 {producto.nombre}\n💲 {producto.precio} {producto.moneda}\n🔗 {producto.link or 'No disponible'}"
        await send_message(chat_id, respuesta)
        return

    # 2. Si no es producto → usar inteligencia conversacional
    if OPENAI_KEY:
        try:
            completion = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente de ventas amable, conversacional, que puede responder como persona en varios idiomas."},
                    {"role": "user", "content": text}
                ]
            )
            respuesta = completion.choices[0].message.content
            await send_message(chat_id, respuesta)
        except Exception as e:
            await send_message(chat_id, f"⚠️ Error con OpenAI: {str(e)}")
    else:
        # Fallback sin IA
        await send_message(chat_id, f"🤖 Recibí tu mensaje: {text}")


# Webhook de Telegram
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        db = SessionLocal()
        await process_message(chat_id, text, db)
        db.close()

    return {"ok": True}


# Root endpoint (para Render healthcheck)
@app.get("/")
async def root():
    return {"message": "🤖 Bot de Ventas inteligente en Render 🚀"}
