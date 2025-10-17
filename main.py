import os, asyncio, httpx, openai
from fastapi import FastAPI, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text

# ───────────────────────────────
# CONFIGURACIÓN GENERAL
# ───────────────────────────────
app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # token corregido
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PUBLIC_URL = os.getenv("PUBLIC_URL")

openai.api_key = OPENAI_API_KEY
engine = create_engine(DATABASE_URL)
scheduler = AsyncIOScheduler()

# ───────────────────────────────
# FUNCIÓN PARA ENVIAR MENSAJES
# ───────────────────────────────
async def enviar_mensaje(chat_id, texto):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload)
            print("Respuesta Telegram:", r.text)
        if r.status_code != 200:
            print("⚠️ Error enviando:", r.status_code, r.text)
    except Exception as e:
        print("Error enviando mensaje:", e)

# ───────────────────────────────
# FUNCIÓN PRINCIPAL DEL BOT
# ───────────────────────────────
async def manejar_mensaje_ventas(data):
    mensaje = data.get("message") or data.get("edited_message") or data.get("callback_query", {}).get("message")
    if not mensaje:
        return

    chat_id = mensaje["chat"]["id"]
    texto = mensaje.get("text", "").strip()
    if not texto:
        return

    texto_lower = texto.lower()

    # ────────────── COMANDOS BÁSICOS ──────────────
    if "hola" in texto_lower or "/start" in texto_lower:
        await enviar_mensaje(chat_id, "¡Hola! Soy tu *bot de ventas inteligente* 🤖💰")
    elif "productos" in texto_lower or "ver productos" in texto_lower:
        await enviar_mensaje(chat_id, "Buscando los productos más vendidos... 🔍")
        await enviar_productos(chat_id)
    else:
        # ────────────── MODO INTELIGENTE (GPT) ──────────────
        try:
            respuesta = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un experto en ventas y atención al cliente. Hablas de forma amigable, útil y profesional."},
                    {"role": "user", "content": texto}
                ]
            )
            respuesta_texto = respuesta.choices[0].message.content
            await enviar_mensaje(chat_id, respuesta_texto)
        except Exception as e:
            await enviar_mensaje(chat_id, f"⚠️ Error al procesar con IA: {e}")

# ───────────────────────────────
# FUNCIÓN PARA ENVIAR PRODUCTOS
# ───────────────────────────────
async def enviar_productos(chat_id):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT nombre, enlace, precio FROM productos ORDER BY fecha DESC LIMIT 5"))
            productos = result.fetchall()

        if not productos:
            await enviar_mensaje(chat_id, "Aún no hay productos cargados 🕐")
            return

        mensaje = "🛍 *Top productos más vendidos:*\n\n"
        for p in productos:
            nombre, enlace, precio = p
            mensaje += f"• [{nombre}]({enlace}) — ${precio}\n"

        await enviar_mensaje(chat_id, mensaje)
    except Exception as e:
        await enviar_mensaje(chat_id, f"⚠️ Error al obtener productos: {e}")

# ───────────────────────────────
# LIMPIEZA AUTOMÁTICA DE PRODUCTOS
# ───────────────────────────────
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
# ENDPOINT DEL WEBHOOK
# ───────────────────────────────
@app.post("/webhook_ventas")
async def webhook_ventas(request: Request):
    data = await request.json()
    await manejar_mensaje_ventas(data)
    return {"ok": True}

# ───────────────────────────────
# INICIO DEL BOT
# ───────────────────────────────
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            params={"url": f"{PUBLIC_URL}/webhook_ventas"},
        )
        print("Webhook respuesta:", resp.text)
    print("🚀 Bot de ventas iniciado correctamente y webhook configurado.")

@app.get("/")
async def home():
    return {"status": "Bot de ventas activo 🚀"}

# ───────────────────────────────
# EJECUCIÓN
# ───────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
    asyncio.get_event_loop().run_forever()
