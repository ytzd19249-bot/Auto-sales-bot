from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

# Variables de entorno en Render (ojo con los nombres exactos)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  
PUBLIC_URL = os.getenv("PUBLIC_URL")  

# Endpoint de prueba
@app.get("/")
async def home():
    return {"message": "🤖 Bot de Ventas funcionando en Render 🚀"}

# Endpoint del Webhook (Telegram manda mensajes aquí)
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Respuesta simple (para probar)
        reply = f"Recibí tu mensaje: {text}"
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": reply}
            )

    return {"ok": True}
