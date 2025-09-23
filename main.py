# main.py
import os
import httpx
from fastapi import FastAPI, Request
from db import SessionLocal, Producto, init_db
from sqlalchemy.orm import Session
from openai import OpenAI

# Inicializar FastAPI
app = FastAPI()

# Inicializar DB
init_db()

# ======================
# Variables de entorno
# ======================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")  # 👈 nombre correcto
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# Inicializar cliente OpenAI
client = OpenAI(api_key=OPENAI_KEY)


# ======================
# Enviar mensaje a Telegram
# ======================
async def send_message(chat_id: int, text: str):
    if not BOT_TOKEN:
        print("❌ ERROR: No se encontró TELEGRAM_TOKEN en las variables de entorno")
        return

    url = f"{BASE_URL}/sendMessage"
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.post(
            url,
            json={"chat_id": chat_id, "text": text}
        )
        if resp.status_code != 200:
            print(f"❌ Error enviando mensaje: {resp.status_code} - {resp.text}")
        else:
            print(f"✅ Mensaje enviado a {chat_id}: {text}")


# ======================
# Procesar mensaje del usuario
# ======================
async def process_message(chat_id: int, text: str, db: Session):
    text_lower = text.lower()

    # 1. Buscar producto en DB
    producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{text_lower}%")).first()
    if producto:
        respuesta = f"📦 {producto.nombre}\n💲 {producto.precio} {producto.moneda}\n🔗 {producto.link or 'No disponible'}"
        await send_message(chat_id, respuesta)
        return

    # 2. Conversación con OpenAI
    if OPENAI_KEY:
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente de ventas amable y conversacional, responde como una persona en varios idiomas."},
                    {"role": "user", "content": text}
                ]
            )
            respuesta = completion.choices[0].message.content
            await send_message(chat_id, respuesta)
        except Exception as e:
            print("⚠️ Error con OpenAI:", str(e))
            await send_message(chat_id, "⚠️ Error con la IA, pero aquí estoy para ayudarte.")
    else:
        # Fallback sin IA
        await send_message(chat_id, f"🤖 Recibí tu mensaje: {text}")


# ======================
# Webhook de Telegram
# ======================
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


# ======================
# Root endpoint
# ======================
@app.get("/")
async def root():
    return {"message": "🤖 Bot de Ventas inteligente en Render 🚀"}
