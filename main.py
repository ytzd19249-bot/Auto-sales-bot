# main.py
import os
import asyncio
from datetime import datetime
import httpx

from fastapi import FastAPI, Request, Header, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ───────────────────────────────
# CONFIGURACIÓN GENERAL
# ───────────────────────────────
app = FastAPI(title="Bot de Ventas - CompraFácil", version="2.0")

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "ventas_admin_12345")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")  # e.g. https://vendedorbt.onrender.com
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
scheduler = AsyncIOScheduler(timezone="America/Costa_Rica")

# ───────────────────────────────
# INICIALIZAR BOT TELEGRAM
# ───────────────────────────────
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ───────────────────────────────
# UTILIDADES DB
# ───────────────────────────────
def ensure_schema():
    """Crea tablas necesarias si no existen (no toca productos)."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                mensaje TEXT,
                respuesta TEXT,
                fecha TIMESTAMP DEFAULT NOW()
            );
        """))

def formatear_producto_row(row):
    """Mapea columnas existentes a las esperadas; no inventa datos."""
    # Intentamos usar columnas 'nuevas' si existen, de lo contrario las de tu tabla original.
    titulo = row.get("titulo") or row.get("nombre") or "Producto"
    precio = row.get("precio")
    categoria = row.get("categoria") or "General"
    link = row.get("link_afiliado") or row.get("link") or "#"
    return titulo, precio, categoria, link

def buscar_productos_por_texto(q: str, limit: int = 5):
    """Busca productos por coincidencia en título/nombre/categoría/descripcion."""
    terms = [t for t in q.lower().split() if len(t) >= 3]
    if not terms:
        return []

    # Construimos OR dinámico seguro (parametrizado) usando ILIKE
    where_clauses = []
    params = {}
    i = 0
    for t in terms:
        like = f"%{t}%"
        where_clauses.append(f"(LOWER(COALESCE(titulo, nombre,'')) ILIKE :p{i} OR LOWER(COALESCE(categoria,'')) ILIKE :p{i} OR LOWER(COALESCE(descripcion,'')) ILIKE :p{i})")
        params[f"p{i}"] = like
        i += 1
    where_sql = " OR ".join(where_clauses)

    sql = f"""
        SELECT
            COALESCE(titulo, nombre)               AS titulo,
            precio,
            COALESCE(categoria, 'General')         AS categoria,
            COALESCE(link_afiliado, link)          AS link_afiliado
        FROM productos
        WHERE {where_sql}
        ORDER BY fecha DESC NULLS LAST, created_at DESC NULLS LAST
        LIMIT :limit;
    """
    params["limit"] = limit

    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]
    return rows

def listar_productos_recientes(limit: int = 5):
    sql = """
        SELECT
            COALESCE(titulo, nombre)               AS titulo,
            precio,
            COALESCE(categoria, 'General')         AS categoria,
            COALESCE(link_afiliado, link)          AS link_afiliado
        FROM productos
        ORDER BY fecha DESC NULLS LAST, created_at DESC NULLS LAST
        LIMIT :limit;
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), {"limit": limit})
        rows = [dict(r._mapping) for r in result.fetchall()]
    return rows

def registrar_conversacion(user_id: int, username: str, mensaje: str, respuesta: str):
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO conversaciones (user_id, username, mensaje, respuesta, fecha)
                    VALUES (:user_id, :username, :mensaje, :respuesta, NOW())
                """),
                {
                    "user_id": user_id,
                    "username": username,
                    "mensaje": mensaje[:4000] if mensaje else None,
                    "respuesta": respuesta[:4000] if respuesta else None,
                },
            )
    except Exception as e:
        print(f"[LOG] No se pudo registrar la conversación: {e}")

# ───────────────────────────────
# ENDPOINT PRINCIPAL / WEBHOOK
# ───────────────────────────────
@app.post("/webhook_ventas")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        print(f"[VENTAS] ⚠️ Error procesando mensaje: {e}")
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
# COMANDOS TELEGRAM
# ───────────────────────────────
async def start_command(update: Update, context):
    texto = (
        "Hola, soy **CompraFácil**, tu asistente de ventas y servicio al cliente. "
        "Estoy disponible 24/7 para ayudarte. ¿Qué estás buscando hoy?"
    )
    await update.message.reply_markdown(texto)

async def listar_productos_cmd(update: Update, context):
    try:
        rows = listar_productos_recientes(limit=10)
        if not rows:
            await update.message.reply_text("Por ahora no hay productos cargados. Vuelve pronto.")
            return

        respuesta = []
        for r in rows:
            titulo = r.get("titulo") or "Producto"
            precio = r.get("precio")
            categoria = r.get("categoria") or "General"
            link = r.get("link_afiliado") or "#"
            linea = (
                f"📦 *{titulo}*\n"
                f"💰 ${precio}\n"
                f"🏷 {categoria}\n"
                f"[Ver producto]({link})"
            )
            respuesta.append(linea)

        await update.message.reply_markdown("\n\n".join(respuesta))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(CommandHandler("productos", listar_productos_cmd))

# ───────────────────────────────
# SERVICIO AL CLIENTE 24/7 (IA + BÚSQUEDA EN DB)
# ───────────────────────────────
# OpenAI (cliente estilo SDK v2)
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    print(f"[IA] No se pudo inicializar OpenAI: {e}")
    openai_client = None

def es_saludo(texto: str) -> bool:
    t = texto.lower().strip()
    saludos = {"hola", "buenas", "buenos días", "buenas tardes", "buenas noches", "hey", "saludos"}
    return t in saludos or any(t.startswith(s) for s in saludos)

def hay_intencion_compra(texto: str) -> bool:
    t = texto.lower()
    claves = ["producto", "tienes", "tenés", "busco", "comprar", "mostrar", "vender", "oferta", "precio", "catalogo", "catálogo", "recomienda", "recomendación"]
    return any(k in t for k in claves)

async def responder_con_productos(update: Update, consulta: str):
    # Busca por texto; si no encuentra nada, devuelve recientes
    rows = buscar_productos_por_texto(consulta, limit=5)
    if not rows:
        rows = listar_productos_recientes(limit=5)

    if not rows:
        await update.message.reply_text("En este momento no hay productos disponibles. ¿Te ayudo con otra consulta?")
        return None

    bloques = []
    for r in rows:
        titulo = r.get("titulo") or "Producto"
        precio = r.get("precio")
        categoria = r.get("categoria") or "General"
        link = r.get("link_afiliado") or "#"
        bloque = (
            f"📦 *{titulo}*\n"
            f"💰 ${precio}\n"
            f"🏷 {categoria}\n"
            f"[Ver producto]({link})"
        )
        bloques.append(bloque)

    texto_md = "Aquí tienes algunas opciones que podrían interesarte:\n\n" + "\n\n".join(bloques)
    await update.message.reply_markdown(texto_md)
    return texto_md

async def responder_ia(update: Update, context):
    user = update.message.from_user
    user_id = user.id if user else None
    username = user.username if user else None
    user_message = (update.message.text or "").strip()

    # Presentación y saludo formal
    if es_saludo(user_message):
        respuesta = "Hola, soy **CompraFácil**, tu asistente de ventas y servicio al cliente. ¿En qué puedo ayudarte hoy?"
        await update.message.reply_markdown(respuesta)
        registrar_conversacion(user_id, username, user_message, respuesta)
        return

    # Intención de consulta de productos
    if hay_intencion_compra(user_message):
        try:
            respuesta = await responder_con_productos(update, user_message)
            registrar_conversacion(user_id, username, user_message, respuesta or "[sin respuesta de productos]")
            return
        except Exception as e:
            print(f"[IA] Error al listar productos: {e}")

    # Conversación general / servicio al cliente con IA
    respuesta_texto = None
    try:
        if openai_client:
            completion = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system",
                     "content": (
                         "Eres 'CompraFácil', un asistente profesional de ventas y servicio al cliente. "
                         "Respondes con respeto, claridad y empatía. "
                         "No inventes productos; si te preguntan por productos, sugiere consultar el catálogo con /productos "
                         "o intenta entender la necesidad para recomendar categorías. "
                         "Usa español neutro, formal. Sé breve y útil."
                     )},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.6,
                max_tokens=220,
            )
            respuesta_texto = (completion.choices[0].message.content or "").strip()
        else:
            # Fallback si no hay API key
            respuesta_texto = "Con gusto te ayudo. ¿Podrías darme más detalles para orientarte mejor?"
    except Exception as e:
        print(f"[IA] Error OpenAI: {e}")
        respuesta_texto = "Disculpa, hubo un inconveniente al procesar tu consulta. ¿Podemos intentarlo de nuevo?"

    await update.message.reply_text(respuesta_texto)
    registrar_conversacion(user_id, username, user_message, respuesta_texto)

# Manejador de mensajes de texto (no comandos)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_ia))

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
    ensure_schema()
    scheduler.start()
    asyncio.create_task(iniciar_bot())

async def iniciar_bot():
    await telegram_app.initialize()
    await telegram_app.start()
    await set_webhook()
    print("[VENTAS] 🤖 Bot de Telegram iniciado correctamente")

async def set_webhook():
    # Pequena espera para asegurar que el servidor ya expone el endpoint
    await asyncio.sleep(3)
    async with httpx.AsyncClient() as client:
        url = f"{PUBLIC_URL}/webhook_ventas"
        try:
            res = await client.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
                params={"url": url},
                timeout=15,
            )
            print("[VENTAS] 🚀 Webhook configurado:", res.json())
        except Exception as e:
            print(f"[VENTAS] ⚠️ Error configurando webhook: {e}")

# ───────────────────────────────
# ENDPOINT RAÍZ
# ───────────────────────────────
@app.get("/")
def root():
    return {"ok": True, "bot": "CompraFácil", "status": "activo"}
