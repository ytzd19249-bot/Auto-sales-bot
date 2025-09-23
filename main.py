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

# =============================
# VARIABLES DE ENTORNO
# =============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_KEY

# Debug prints
print("🚀 Bot iniciado")
print("🔑 TELEGRAM_TOKEN:", "Cargado ✅" if TELEGRAM_TOKEN else "❌ NO encontrado")
print("🔑 OPENAI_API_KEY:", "Cargada ✅" if OPENAI_KEY else "❌ NO encontrada")


# =============================
# FUNCIONES
# =============================

# Enviar mensaje a Telegram
async def send_message(chat_id: int, text: str):
    url = f"{BASE_URL}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            if resp.status_code != 200:
                print(f"❌ Error enviando mensaje: {resp.status_code} {resp.text}")
            else:
                print(f"✅ Mensaje enviado a {chat_id}: {text}")
    except Exception as e:
        print("❌ ERROR inesperado al enviar mensaje:", str(e))


# Procesar mensaje del usuario
async def process_message(chat_id: int, text: str, db: Session):
    text_lower = text.lower()

    # 1. Buscar producto en DB
    producto = db.query(Producto).filter(Producto.nombre.ilike(f"%{text_lower}%")).first()
    if producto:
        respuesta = (
            f"📦 {producto.nombre}\n"
            f"💲 {producto.precio} {producto.moneda}\n"
            f"🔗 {producto.link or 'No disponible'}"
        )
        await send_message(chat_id, respuesta)
        return

    # 2. Si no hay producto → responder con IA (si hay clave OpenAI)
    if OPENAI_KEY:
        try:
            completion = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un asistente de ventas amable y natural, respondes como una persona en varios idiomas."
                    },
                    {"role": "user", "content": text}
                ]
            )
            respuesta = completion.choices[0].message.content
            await send_message(chat_id, respuesta)
        except Exception as e:
            print("⚠️ Error con OpenAI:", str(e))
            await send_message(chat_id, "⚠️ No pude usar la IA, pero aquí estoy para ayudarte.")
    else:
        # Fallback sin IA
        await send_message(chat_id, f"🤖 Recibí tu mensaje: {text}")


# =============================
# ENDPOINTS
# =============================

# Webhook de Telegram
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    print("📩 Update recibido:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        db = SessionLocal()
        await process_message(chat_id, text, db)
        db.close()

    return {"ok": True}


# Root endpoint (Render healthcheck)
@app.get("/")
async def root():
    return {"message": "🤖 Bot de Ventas inteligente en Render 🚀"}
