# main.py
import os
import re
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx
from typing import Optional

from db import SessionLocal, Producto, init_db

# Inicializar tablas al arrancar
init_db()

app = FastAPI(title="Bot de Ventas — API")

# Variables de entorno (poner en Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")            # token del bot de ventas
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")              # token usado por bot investigador para actualizar catálogo (opcional)
PUBLIC_URL = os.getenv("PUBLIC_URL", "")                # ej: https://auto-sales-bot.onrender.com (opcional, para set_webhook)

if not TELEGRAM_TOKEN:
    # No romper la app si falta token (pero avisamos)
    print("WARNING: TELEGRAM_TOKEN no está configurado en variables de entorno.")

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ---------- Util: enviar mensaje a Telegram (async)
async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    if not TELEGRAM_TOKEN:
        return None
    url = f"{BASE_TELEGRAM_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json=payload)
            return resp.json()
        except Exception:
            return None


# ---------- Procesar mensaje: lógica conversacional
def procesar_mensaje(texto: str) -> str:
    t = texto.lower().strip()

    # SALUDOS
    if re.search(r"\b(hola|buenas|hey|hi|qué tal|buen día|buenos días|buenas tardes)\b", t):
        return "👋 ¡Hola! Soy tu asistente de ventas. ¿Te muestro el catálogo o buscas algo específico?"

    # PREGUNTAS POR PRODUCTOS / CATALOGO
    if re.search(r"\b(producto|productos|catálogo|catalogo|venden|ofrecen|tienen)\b", t):
        db = SessionLocal()
        try:
            productos = db.query(Producto).filter(Producto.activo == True).all()
        finally:
            db.close()

        if not productos:
            return "😔 Por ahora no hay productos cargados. El catálogo se actualiza automáticamente."
        lista = "\n".join([f"🔹 {p.id}. {p.nombre} — {p.precio} {p.moneda}" for p in productos[:20]])
        return f"📦 Estos son los productos disponibles ahora mismo:\n\n{lista}\n\nEscribe el número del producto para más detalles."

    # SI PREGUNTA POR UN NÚMERO (DETALLE DE PRODUCTO)
    m = re.match(r"^\s*(\d{1,5})\s*$", t)
    if m:
        pid = int(m.group(1))
        db = SessionLocal()
        try:
            producto = db.query(Producto).filter(Producto.id == pid).first()
        finally:
            db.close()
        if producto:
            if producto.activo:
                desc = producto.descripcion or "Sin descripción."
                link = producto.link or "Enlace no disponible."
                return f"✅ *{producto.nombre}*\n{desc}\nPrecio: {producto.precio} {producto.moneda}\nCompra: {link}"
            else:
                return f"🚫 El producto *{producto.nombre}* ya no está disponible."
        else:
            return "❓ No encontré ese producto. Pregunta por el catálogo si quieres ver la lista."

    # PRECIOS / COSTOS
    if re.search(r"\b(precio|cuesta|vale|precio de|tarifa|costar)\b", t):
        return "💲 Puedo darte precios exactos si me dices el nombre o el id del producto (por ejemplo: 12)."

    # RECOMENDACIONES
    if re.search(r"\b(qué me recomiendas|recomiéndame|qué recomiendas|recomienda)\b", t):
        db = SessionLocal()
        try:
            producto = db.query(Producto).filter(Producto.activo == True).order_by(Producto.created_at.desc()).first()
        finally:
            db.close()
        if producto:
            return f"😉 Te recomiendo *{producto.nombre}* — {producto.descripcion or 'Producto destacado'} — {producto.precio} {producto.moneda}. ¿Te interesa?"
        else:
            return "🤔 No tengo productos cargados para recomendar aun."

    # OFERTAS / DESCUENTOS
    if re.search(r"\b(oferta|descuento|promo|promoción|promocion)\b", t):
        return "🔥 Tenemos promos puntuales. Dime el producto (nombre o id) y verifico si tiene descuento."

    # CIERRE / AGRADECIMIENTO
    if re.search(r"\b(gracias|ok|perfecto|listo|vale|pura vida)\b", t):
        return "🙏 ¡Con gusto! Si necesitas algo más, dime. Estoy aquí para ayudarte."

    # FALLBACK: pregunta si quiere ver catálogo
    return "🤔 No estoy seguro de eso. ¿Quieres que te muestre el catálogo de productos? (escribe: productos / o solo escribe el número del producto)"



# ---------- Endpoint webhook que Telegram llamará (POST)
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(content={"ok": False, "error": "invalid JSON"}, status_code=400)

    if "message" not in update:
        # Podemos aceptar otros updates (callback_query, etc.)
        return JSONResponse(content={"ok": True})

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    if not text:
        await send_message(chat_id, "📝 Solo puedo procesar mensajes de texto por ahora.")
        return JSONResponse(content={"ok": True})

    # Procesar de forma conversacional
    respuesta = procesar_mensaje(text)
    await send_message(chat_id, respuesta)
    return JSONResponse(content={"ok": True})


# ---------- Admin endpoint: actualizar productos (usado por Bot Investigador)
@app.post("/admin/update_products")
async def admin_update_products(request: Request, x_admin_token: Optional[str] = Header(None)):
    """
    Expects JSON body like:
    {
      "10": {"nombre":"Producto X","precio":30,"moneda":"USD","link":"https://...","descripcion":"...","source":"Hotmart"},
      "11": {...}
    }
    Header x-admin-token must match ADMIN_TOKEN
    """
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="ADMIN_TOKEN not configured")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    data = await request.json()

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid body")

    db = SessionLocal()
    try:
        updated = []
        for pid_str, info in data.items():
            try:
                pid = int(pid_str)
            except Exception:
                # If keys are strings that are not numeric, skip or create with autoincrement
                pid = None

            if pid:
                prod = db.query(Producto).filter(Producto.id == pid).first()
            else:
                prod = None

            if prod:
                # actualizar campos
                prod.nombre = info.get("nombre", prod.nombre)
                prod.descripcion = info.get("descripcion", prod.descripcion)
                prod.precio = float(info.get("precio", prod.precio or 0))
                prod.moneda = info.get("moneda", prod.moneda or "USD")
                prod.link = info.get("link", prod.link)
                prod.source = info.get("source", prod.source)
                prod.activo = info.get("activo", prod.activo)
            else:
                # crear nuevo producto
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


# ---------- Helper: set webhook desde el navegador (opcional)
@app.get("/set_webhook")
async def set_webhook():
    """
    Llama al método setWebhook de Telegram usando PUBLIC_URL (si está configurado).
    Use: set PUBLIC_URL en Render (ej: https://auto-sales-bot.onrender.com)
    """
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
    return {"status": "Bot de Ventas — listo y escuchando"}
