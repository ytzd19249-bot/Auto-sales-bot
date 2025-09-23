import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from db import SessionLocal, Producto

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ----------- FUNCIONES AUXILIARES -----------
async def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})

# ----------- ENDPOINT WEBHOOK -----------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").strip()

        # Interacción más natural tipo vendedor
        if text.lower() in ["hola", "hi", "hello"]:
            await send_message(chat_id, "👋 ¡Hola! Bienvenido, ¿te interesa conocer nuestros cursos disponibles?")

        elif "curso" in text.lower() or "product" in text.lower():
            db = SessionLocal()
            productos = db.query(Producto).filter(Producto.activo == True).all()
            db.close()

            if not productos:
                await send_message(chat_id, "🚫 No tengo productos activos en este momento.")
            else:
                lista = "\n".join([f"🔹 {p.nombre} - ${p.precio}" for p in productos])
                await send_message(chat_id, f"📦 Aquí tienes lo que tengo disponible:\n{lista}\n👉 ¿Quieres que te envíe el link de compra?")

        else:
            await send_message(chat_id, "🙂 Entiendo, cuéntame qué estás buscando y te ayudo.")

    return JSONResponse(content={"ok": True})
