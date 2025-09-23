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

# Variables de entorno
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "AQUI_VA_TU_TOKEN_REAL")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_KEY


# Enviar mensaje a Telegram
async def send_message(chat_id: int, text: str):
    url = f"{BASE_URL}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})


# Procesar mensaje
async def process_message(chat_id: int, text: str, db: Session):
    text_lower = text.lower()

    # Buscar producto por nombre
    producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{text_lower}%")).first()
    if producto:
        respuesta = (
            f"📦 {producto.nombre}\n"
            f"💲 {producto.precio} {producto.moneda}\n"
            f"🔗 {producto.link or 'No disponible'}"
        )
        await send_message(chat_id, respuesta)
        return

    # Conversación inteligente con OpenAI
    if OPENAI_KEY:
        try:
            completion = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un asesor de ventas amable y natural. Responde como una persona real, en el mismo idioma que el usuario. Puedes dar detalles de productos, explicar precios y mantener una charla fluida."},
                    {"role": "user", "content": text}
                ]
            )
            respuesta = completion.choices[0].message.content
            await send_message(chat_id, respuesta)
        except Exception as e:
            await send_message(chat_id, "⚠️ Hubo un problema al procesar tu mensaje.")
    else:
        await send_message(chat_id, f"🤖 Recibí tu mensaje: {text}")


# Webhook
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


# Root endpoint
@app.get("/")
async def root():
    return {"message": "🤖 Bot de Ventas con inteligencia conversacional listo 🚀"}
