import os, asyncio, httpx, openai
from fastapi import FastAPI, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text

# ───────────────────────────────
# CONFIGURACIÓN GENERAL
# ───────────────────────────────
app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PUBLIC_URL = os.getenv("PUBLIC_URL")  # URL pública de Render
openai.api_key = OPENAI_API_KEY

engine = create_engine(DATABASE_URL)

# ───────────────────────────────
# FUNCIONES TELEGRAM
# ───────────────────────────────
async def enviar_mensaje(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

# ───────────────────────────────
# LÓGICA DEL BOT DE VENTAS
# ───────────────────────────────
async def manejar_mensaje_ventas(data):
    if "message" not in data:
        return

    chat_id = data["message"]["chat"]["id"]
    texto = data["message"].get("text", "").lower()

    if "hola" in texto:
        await enviar_mensaje(chat_id, "¡Hola! Soy el *bot de ventas* 💰")
    elif "productos" in texto or "ver productos" in texto:
        await enviar_mensaje(chat_id, "Buscando los productos más vendidos... 🔍")
        await enviar_productos(chat_id)
    else:
        await enviar_mensaje(chat_id, "No entendí eso, pero estoy aquí para ayudarte a vender 😎")

# ───────────────────────────────
# FUNCIÓN PARA ENVIAR PRODUCTOS
# ───────────────────────────────
async def enviar_productos(chat_id):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT nombre, enlace, precio FROM productos ORDER BY fecha DESC LIMIT 5"))
            productos = result.fetchall()

        if not productos:
            await enviar_mensaje(chat_id, "Aún no hay productos cargados por el bot investigador 🕐")
            return

        mensaje = "🛍 *Top productos más vendidos:*\n\n"
        for p in productos:
            nombre, enlace, precio = p
            mensaje += f"• [{nombre}]({enlace}) — ${precio}\n"

        await enviar_mensaje(chat_id, mensaje)
    except Exception as e:
        await enviar_mensaje(chat_id, f"⚠️ Error al obtener productos: {e}")

# ───────────────────────────────
# ENDPOINT DEL WEBHOOK DE VENTAS
# ───────────────────────────────
@app.post("/webhook_ventas")
async def webhook_ventas(request: Request):
    data = await request.json()
    await manejar_mensaje_ventas(data)
    return {"ok": True}

# ───────────────────────────────
# CONFIGURACIÓN DEL SCHEDULER (CADA 12 HORAS)
# ───────────────────────────────
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", hours=12)
async def ciclo_ventas():
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                DELETE FROM productos
                WHERE fecha < NOW() - INTERVAL '120 days' AND vendidos = 0
            """))
            conn.commit()
        print("🧹 Limpieza de productos antiguos completada.")
    except Exception as e:
        print(f"Error en limpieza automática: {e}")

# ───────────────────────────────
# INICIO DEL BOT
# ───────────────────────────────
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    async with httpx.AsyncClient() as client:
        await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            params={"url": f"{PUBLIC_URL}/webhook_ventas"},
        )
    print("🚀 Bot de ventas iniciado correctamente y webhook configurado.")

@app.get("/")
def home():
    return {"status": "Bot de ventas activo 🚀"}

# ───────────────────────────────
# EJECUCIÓN LOCAL
# ───────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
