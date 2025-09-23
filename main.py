# main.py
import os
import re
import json
import logging
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx
from typing import Optional
from db import SessionLocal, Producto, init_db

# Inicializar tablas
init_db()

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bot de Ventas — API")

# Variables de entorno
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "")

if not TELEGRAM_TOKEN:
    logger.warning("⚠️ TELEGRAM_TOKEN no está configurado.")

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ---------- Utilidad para enviar mensajes
async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    if not TELEGRAM_TOKEN:
        return None
    url = f"{BASE_TELEGRAM_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json=payload)
            logger.info(f"📤 Enviado a {chat_id}: {text}")
            return resp.json()
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje: {e}")
            return None


# ---------- Procesamiento de mensajes
def procesar_mensaje(texto: str, lang: str = "es") -> str:
    t = texto.lower().strip()
    logger.info(f"📥 Mensaje recibido: {texto}")

    # Español / Inglés básicos
    saludos = [r"\b(hola|buenas|hey|hi|hello|qué tal)\b"]
    catalogo = [r"\b(producto|productos|catalogo|catalogue|catalog)\b"]
    gracias = [r"\b(gracias|ok|perfecto|thanks|thank you)\b"]

    if any(re.search(p, t) for p in saludos):
        return "👋 ¡Hola! Soy tu asistente de ventas. ¿Quieres ver el catálogo de productos?"

    if any(re.search(p, t) for p in catalogo):
        db = SessionLocal()
        try:
            productos = db.query(Producto).filter(Producto.activo == True).all()
        finally:
            db.close()
        if not productos:
            return "😔 No hay productos cargados aún."
        lista = "\n".join([f"🔹 {p.id}. {p.nombre} — {p.precio} {p.moneda}" for p in productos[:10]])
        return f"📦 Catálogo disponible:\n\n{lista}\n\nEscribe el número del producto para más detalles."

    # Números = detalle de producto
    m = re.match(r"^\s*(\d{1,5})\s*$", t)
    if m:
        pid = int(m.group(1))
        db = SessionLocal()
        try:
            producto = db.query(Producto).filter(Producto.id == pid).first()
        finally:
            db.close()
        if producto and producto.activo:
            desc = producto.descripcion or "Sin descripción."
            link = producto.link or "No hay enlace."
            return f"✅ *{producto.nombre}*\n{desc}\nPrecio: {producto.precio} {producto.moneda}\nCompra aquí: {link}"
        else:
            return "❓ No encontré ese producto."

    if any(re.search(p, t) for p in gracias):
        return "🙏 ¡Con gusto! Estoy para ayudarte."

    # Fallback — siempre responde
    return "🤔 No entendí bien, pero dime si quieres ver el catálogo de productos."


# ---------- Webhook de Telegram
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(content={"ok": False, "error": "invalid JSON"}, status_code=400)

    logger.info(f"🔔 Update recibido: {json.dumps(update)}")

    if "message" not in update:
        return JSONResponse(content={"ok": True})

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if not text:
        await send_message(chat_id, "📝 Solo proceso mensajes de texto.")
        return JSONResponse(content={"ok": True})

    respuesta = procesar_mensaje(text)
    await send_message(chat_id, respuesta)
    return JSONResponse(content={"ok": True})


# ---------- Admin update products
@app.post("/admin/update_products")
async def admin_update_products(request: Request, x_admin_token: Optional[str] = Header(None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid body")

    db = SessionLocal()
    try:
        updated = []
        for pid_str, info in data.items():
            pid = None
            try:
                pid = int(pid_str)
            except:
                pass

            if pid:
                prod = db.query(Producto).filter(Producto.id == pid).first()
            else:
                prod = None

            if prod:
                prod.nombre = info.get("nombre", prod.nombre)
                prod.descripcion = info.get("descripcion", prod.descripcion)
                prod.precio = float(info.get("precio", prod.precio or 0))
                prod.moneda = info.get("moneda", prod.moneda or "USD")
                prod.link = info.get("link", prod.link)
                prod.source = info.get("source", prod.source)
                prod.activo = info.get("activo", prod.activo)
            else:
                new = Producto(
                    nombre=info.get("nombre", "Sin nombre"),
                    descripcion=info.get("descripcion", ""),
                    precio=float(info.get("precio", 0)),
                    moneda=info.get("moneda", "USD"),
                    link=info.get("link"),
                    source=info.get("source"),
                    activo=info.get("activo", True),
                )
                db.add(new)
            updated.append(pid_str)
        db.commit()
    finally:
        db.close()

    return {"ok": True, "updated": updated}


# ---------- Helper: set webhook
@app.get("/set_webhook")
async def set_webhook():
    if not PUBLIC_URL or not TELEGRAM_TOKEN:
        raise HTTPException(status_code=400, detail="PUBLIC_URL o TELEGRAM_TOKEN faltan")
    webhook_url = f"{PUBLIC_URL}/webhook"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data={"url": webhook_url})
        return JSONResponse(content=resp.json())


# ---------- Home
@app.get("/")
def root():
    return {"status": "🤖 Bot de Ventas funcionando en Render 🚀"}
