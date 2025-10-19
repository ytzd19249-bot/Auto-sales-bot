# main.py
import os
import asyncio
import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text
from telegram import Update
from telegram.ext import Application, CommandHandler
from datetime import datetime

# ───────────────────────────────
# CONFIGURACIÓN GENERAL
# ───────────────────────────────
app = FastAPI(title="Bot de Ventas", version="1.0")

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "ventas_admin_12345")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")  # https://vendedorbt.onrender.com

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
scheduler = AsyncIOScheduler(timezone="America/Costa_Rica")

# ───────────────────────────────
# INICIALIZAR BOT TELEGRAM
# ───────────────────────────────
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ───────────────────────────────
# ENDPOINT PRINCIPAL / WEBHOOK
# ───────────────────────────────
@app.post("/webhook_ventas")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

# ───────────────────────────────
# ENDPOINT PARA RECIBIR PRODUCTOS DEL INVESTIGADOR
# ───────────────────────────────
@app.post("/ingestion/productos")
async def recibir_productos(req: Request, authorization: str = Header(None)):
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="No autorizado")

    data = await req.json()
    productos = data.get("productos", [])

    if not productos:
        return {"ok": False, "mensaje": "Sin productos recibidos"}

    insertados = 0
    for p in productos:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO productos (titulo, precio, categoria, link_afiliado, fecha)
                        VALUES (:titulo, :precio, :categoria, :link_afiliado, NOW())
                        ON CONFLICT (titulo) DO UPDATE
                        SET precio = EXCLUDED.precio,
                            categoria = EXCLUDED.categoria,
                            link_afiliado = EXCLUDED.link_afiliado,
                            fecha = NOW();
                    """),
                    {
                        "titulo": p.get("titulo"),
                        "precio": p.get("precio"),
                        "categoria": p.get("categoria"),
                        "link_afiliado": p.get("link_afiliado"),
                    },
                )
                insertados += 1
        except Exception as e:
            print(f"[VENTAS] ❌ Error guardando producto: {e}")

    print(f"[VENTAS] ✅ Productos insertados/actualizados: {insertados}")
    return {"ok": True, "insertados": insertados}

# ───────────────────────────────
# COMANDO /productos EN TELEGRAM
# ───────────────────────────────
async def listar_productos(update: Update, context):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT titulo, precio, categoria, link_afiliado
                FROM productos
                ORDER BY fecha DESC
                LIMIT 10;
            """))
            productos = result.fetchall()

        if not productos:
            await update.message.reply_text("No hay productos registrados todavía.")
            return

        for p in productos:
            titulo, precio, categoria, link = p
            texto = (
                f"📦 *{titulo}*\n"
                f"💰 Precio: ${precio}\n"
                f"🏷 Categoría: {categoria}\n"
                f"[🔗 Ver producto]({link})"
            )
            await update.message.reply_markdown(texto)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

telegram_app.add_handler(CommandHandler("productos", listar_productos))

# ───────────────────────────────
# LIMPIEZA AUTOMÁTICA DE PRODUCTOS VIEJOS
# ───────────────────────────────
def limpiar_productos_viejos():
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM productos
                    WHERE fecha < NOW() - INTERVAL '120 days';
                """)
            )
        print(f"[VENTAS] 🧹 Limpieza completada ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    except Exception as e:
        print(f"[VENTAS] ⚠️ Error limpiando productos: {e}")

@scheduler.scheduled_job("interval", hours=12)
def ciclo_limpieza():
    limpiar_productos_viejos()

# ───────────────────────────────
# ARRANQUE DEL SERVICIO Y WEBHOOK
# ───────────────────────────────
@app.on_event("startup")
async def start():
    scheduler.start()
    asyncio.create_task(iniciar_bot())

async def iniciar_bot():
    await telegram_app.initialize()
    await telegram_app.start()
    await set_webhook()
    print("[VENTAS] 🤖 Bot de Telegram iniciado correctamente")

async def set_webhook():
    await asyncio.sleep(5)
    async with httpx.AsyncClient() as client:
        url = f"{PUBLIC_URL}/webhook_ventas"
        res = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={url}"
        )
        print("[VENTAS] 🚀 Webhook configurado:", res.json())

# ───────────────────────────────
# ENDPOINT RAÍZ
# ───────────────────────────────
@app.get("/")
def root():
    return {"ok": True, "bot": "ventas", "status": "activo"}
