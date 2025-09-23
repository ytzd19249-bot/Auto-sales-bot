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


def buscar_productos_en_db():
    """Consulta productos en la base de datos compartida (los que guarda el bot investigador)."""
    db = SessionLocal()
    productos = db.query(Producto).filter(Producto.activo == True).all()
    db.close()
    return productos


def generar_respuesta(texto: str):
    """Genera una respuesta simple estilo vendedor educado y multilenguaje básico."""
    texto = texto.lower()

    # Respuestas básicas
    if any(palabra in texto for palabra in ["hola", "buenas", "hi", "hello"]):
        return "👋 ¡Hola! Bienvenido a nuestra tienda digital. ¿Buscas algún curso o producto en especial?"

    if any(palabra in texto for palabra in ["precio", "cuánto", "cost", "how much"]):
        return "💰 Claro, indícame qué producto te interesa y te doy el precio."

    if any(palabra in texto for palabra in ["gracias", "thank you", "thx"]):
        return "🙏 Con mucho gusto, estoy aquí para ayudarte."

    # Consultar productos
    productos = buscar_productos_en_db()
    if productos:
        lista = "\n".join([f"🔹 {p.nombre} - ${p.precio}" for p in productos])
        return f"📦 Estos son los productos disponibles:\n{lista}\n👉 Dime cuál te interesa y te paso el enlace de compra."
    else:
        return "🚫 Por el momento no hay productos disponibles. Vuelve pronto. 😉"


# ----------- ENDPOINT WEBHOOK -----------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        texto = data["message"].get("text", "")

        respuesta = generar_respuesta(texto)
        await send_message(chat_id, respuesta)

    return JSONResponse(content={"ok": True})
