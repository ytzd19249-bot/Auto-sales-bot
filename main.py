# main.py
import os, asyncio, httpx, openai
from fastapi import FastAPI, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text

# ───────────────────────────────
#  CONFIGURACIÓN
# ───────────────────────────────
app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")           # completa en Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")       # completa en Render
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")       # completa en Render
openai.api_key = OPENAI_API_KEY

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# ───────────────────────────────
#  FUNCIONES DE BASE DE DATOS
# ───────────────────────────────
def obtener_productos():
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT nombre, precio, moneda, fuente
            FROM productos
            ORDER BY created_at DESC
            LIMIT 5;
        """)).fetchall()
    return [f"{r[0]} - {r[1]} {r[2]} ({r[3]})" for r in result]

def limpiar_viejos():
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM productos
            WHERE created_at < NOW() - INTERVAL '120 days';
        """))
    print("🧹 Productos viejos eliminados.")

# ───────────────────────────────
#  CICLO AUTOMÁTICO
# ───────────────────────────────
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", hours=12)
def ciclo_automatico():
    limpiar_viejos()
    print("🔁 Ciclo automático ejecutado.")

scheduler.start()

# ───────────────────────────────
#  IA PROFESIONAL
# ───────────────────────────────
def responder_con_ia(texto_usuario):
    prompt = f"""
Eres el asistente de ventas oficial de Josue, especializado en atención profesional a clientes.
Tu tono debe ser respetuoso, confiado y claro. Evita chistes o informalidades.
Responde siempre con precisión y orientación al cliente, ofreciendo ayuda real.
Si te preguntan por productos, habla de lo que está disponible en la base de datos.
Texto del cliente: "{texto_usuario}"
"""
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Eres un asesor de ventas serio y profesional."},
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content.strip()

# ───────────────────────────────
#  WEBHOOK TELEGRAM
# ───────────────────────────────
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    texto = (message.get("text") or "").lower()

    if not chat_id or not texto:
        return {"ok": True}

    if "hola" in texto or "buenas" in texto:
        await enviar_mensaje(chat_id, "Buen día. Soy el asistente de ventas de Josue, ¿en qué puedo ayudarle?")
    elif "productos" in texto or "catálogo" in texto:
        lista = obtener_productos()
        if lista:
            texto_resp = "📦 Productos disponibles:\n" + "\n".join(lista)
        else:
            texto_resp = "En este momento no hay productos registrados."
        await enviar_mensaje(chat_id, texto_resp)
    else:
        respuesta = responder_con_ia(texto)
        await enviar_mensaje(chat_id, respuesta)

    return {"ok": True}

# ───────────────────────────────
#  FUNCIÓN DE ENVÍO
# ───────────────────────────────
async def enviar_mensaje(chat_id, texto):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto}
        )

# ───────────────────────────────
#  RUTA RAÍZ
# ───────────────────────────────
@app.get("/")
def home():
    return {"status": "bot de ventas activo 🚀"}
