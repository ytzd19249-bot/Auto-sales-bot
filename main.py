from fastapi import FastAPI, Request
import httpx
import os
from openai import OpenAI

app = FastAPI()

# 🔑 Variables de entorno (ponerlas en Render)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Cliente de OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# Diccionario para guardar idioma por chat
user_languages = {}

async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as http_client:
        await http_client.post(TELEGRAM_API_URL, json={"chat_id": chat_id, "text": text})

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")

        if user_text.startswith("/start"):
            await send_message(chat_id, "👋 Hola mae, bienvenido a CompraFácil Bot ⚡")
            return {"ok": True}

        elif user_text.startswith("/products"):
            await send_message(chat_id, "📦 Tenemos: Celulares, Laptops y Audífonos.")
            return {"ok": True}

        else:
            try:
                # Si no tenemos idioma guardado → detectar
                if chat_id not in user_languages:
                    detection = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Detecta el idioma del siguiente texto y responde solo con el nombre del idioma en inglés (ej: Spanish, English, French, etc.)."},
                            {"role": "user", "content": user_text}
                        ]
                    )
                    detected_lang = detection.choices[0].message.content.strip()
                    user_languages[chat_id] = detected_lang

                # Responder en el idioma detectado
                lang = user_languages[chat_id]
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"Eres un asistente de ventas amable. Responde SIEMPRE en {lang}."},
                        {"role": "user", "content": user_text}
                    ]
                )
                bot_reply = response.choices[0].message.content
                await send_message(chat_id, bot_reply)

            except Exception as e:
                await send_message(chat_id, f"⚠️ Error con OpenAI: {str(e)}")

    return {"ok": True}
