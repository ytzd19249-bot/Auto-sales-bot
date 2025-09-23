# main.py
import os
from fastapi import FastAPI, Request
import httpx
from db import SessionLocal, init_db, Producto

# Inicializar app
app = FastAPI()

# Inicializar base de datos
init_db()

# Leer token de Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ Falta TELEGRAM_TOKEN en variables de entorno")

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ====== ENDPOINT PRINCIPAL ======
@app.get("/")
def home():
    return {"message": "🤖 Bot de Ventas funcionando en Render 🚀"}

# ====== WEBHOOK TELEGRAM ======
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").strip()

        response_text = procesar_mensaje(text)

        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": response_text
            })

    return {"ok": True}

# ====== LÓGICA DE RESPUESTA ======
def procesar_mensaje(text: str) -> str:
    """ Responde inteligentemente a mensajes del usuario """
    if text.lower() in ["/start", "hola", "buenas"]:
        return "👋 Hola, soy tu Bot de Ventas. Preguntame por un producto o escribe 'lista' para ver los disponibles."

    if text.lower() == "lista":
        db = SessionLocal()
        productos = db.query(Producto).filter(Producto.activo == True).all()
        db.close()
        if not productos:
            return "📦 No hay productos disponibles todavía."
        lista = "\n".join([f"- {p.nombre} (${p.precio} {p.moneda})" for p in productos])
        return f"🛍️ Productos disponibles:\n{lista}"

    return f"🤖 No entendí '{text}', pero pronto aprenderé más."
