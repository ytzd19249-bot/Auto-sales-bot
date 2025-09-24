# main.py
import os
import re
import httpx
import openai
from fastapi import FastAPI, Request, HTTPException
from db import SessionLocal, Producto, init_db
from sqlalchemy.orm import Session

app = FastAPI(title="Bot de Ventas - CompraFácil")

# init DB (crea tablas si no existen)
init_db()

# ENV (poner en Render)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")          # token del bot de Telegram
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")        # clave OpenAI (opcional, mejora respuestas)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")          # token que usa el bot investigador para actualizar catálogo (opcional)
PUBLIC_URL = os.getenv("PUBLIC_URL", "")            # ej: https://auto-sales-bot.onrender.com

BASE_TELEGRAM = f"https://api.telegram.org/bot{BOT_TOKEN}"

# configurar OpenAI si existe
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# util — enviar mensaje simple a Telegram
async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    if not BOT_TOKEN:
        return None
    url = f"{BASE_TELEGRAM}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.post(url, json=payload)
            return r.json()
        except Exception:
            return None

# lógica conversacional / manejo productos
def normalize_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())

async def handle_user_message(chat_id: int, text: str, db: Session):
    t = normalize_text(text)

    # SALUDOS simples
    if re.search(r"\b(hola|buenas|buenos días|buenas tardes|buenas noches|hey)\b", t):
        return await send_message(chat_id, "👋 ¡Hola! Soy tu asistente de ventas. ¿En qué te ayudo hoy?")

    # PEDIR CATÁLOGO
    if re.search(r"\b(producto|productos|catálogo|catalogo|qué tienen|qué venden|tienen)\b", t):
        productos = db.query(Producto).filter(Producto.activo == True).order_by(Producto.created_at.desc()).limit(50).all()
        if not productos:
            return await send_message(chat_id, "📭 Por ahora no hay productos disponibles. El catálogo se actualiza automáticamente.")
        lines = [f"{p.id}. {p.nombre} — {p.precio} {p.moneda}" for p in productos]
        text_out = "🛍️ Productos disponibles:\n\n" + "\n".join(lines[:20]) + "\n\nEscribe el número del producto para ver detalles."
        return await send_message(chat_id, text_out)

    # SI EL MENSAJE ES UN NÚMERO -> detalle del producto
    m = re.match(r"^(\d+)$", t)
    if m:
        pid = int(m.group(1))
        prod = db.query(Producto).filter(Producto.id == pid).first()
        if not prod:
            return await send_message(chat_id, "❌ No encontré ese producto. Escribí 'productos' para ver la lista.")
        if not prod.activo:
            return await send_message(chat_id, f"🚫 {prod.nombre} no está disponible.")
        detail = f"✅ *{prod.nombre}*\n{prod.descripcion or 'Sin descripción.'}\nPrecio: {prod.precio} {prod.moneda}\nCompra: {prod.link or 'Enlace no disponible.'}"
        return await send_message(chat_id, detail)

    # SI HAY CLAVE OPENAI -> usar IA conversacional para responder (multi-idioma)
    if OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # si su plan no tiene, cambiar a gpt-3.5-turbo u otro disponible
                messages=[
                    {"role": "system", "content": "Eres un vendedor amable, claro y profesional. Responde como una persona en el idioma del usuario. Si es pregunta sobre un producto, pide el id o muestra catálogo."},
                    {"role": "user", "content": text}
                ],
                max_tokens=400,
                temperature=0.6,
            )
            answer = resp["choices"][0]["message"]["content"]
            return await send_message(chat_id, answer)
        except Exception as e:
            # fallback legible si OpenAI falla
            await send_message(chat_id, "⚠️ Error en IA. Te respondo rápidamente: " + (text[:300] if text else ""))
            return

    # fallback sin IA
    return await send_message(chat_id, f"🤖 Recibí tu mensaje: {text}\n(Escribe 'productos' para ver el catálogo.)")

# Webhook principal que Telegram llamará (POST)
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    if "message" not in update:
        return {"ok": True}

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    db = SessionLocal()
    try:
        await handle_user_message(chat_id, text, db)
    finally:
        db.close()

    return {"ok": True}

# Endpoint admin para actualizar catálogo (usado por Bot Investigador)
@app.post("/admin/update_products")
async def admin_update_products(request: Request):
    token = request.headers.get("x-admin-token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid body")
    db = SessionLocal()
    updated = []
    try:
        for k, v in data.items():
            # si k es numérico, intentar actualizar por id; si no, crear nuevo
            try:
                pid = int(k)
            except:
                pid = None
            if pid:
                prod = db.query(Producto).filter(Producto.id == pid).first()
            else:
                prod = None
            if prod:
                prod.nombre = v.get("nombre", prod.nombre)
                prod.descripcion = v.get("descripcion", prod.descripcion)
                prod.precio = float(v.get("precio", prod.precio or 0))
                prod.moneda = v.get("moneda", prod.moneda or "USD")
                prod.link = v.get("link", prod.link)
                prod.source = v.get("source", prod.source)
                prod.activo = v.get("activo", prod.activo)
            else:
                new = Producto(
                    nombre=v.get("nombre", "Sin nombre"),
                    descripcion=v.get("descripcion", ""),
                    precio=float(v.get("precio", 0)),
                    moneda=v.get("moneda", "USD"),
                    link=v.get("link"),
                    source=v.get("source"),
                    activo=v.get("activo", True),
                )
                db.add(new)
            updated.append(k)
        db.commit()
    finally:
        db.close()
    return {"ok": True, "updated": updated}

@app.get("/")
def root():
    return {"status": "ok", "message": "Bot de Ventas funcionando 🚀"}
