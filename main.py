# main.py
import os
import json
import asyncio
from typing import Optional, List
from datetime import datetime

import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse

from db import SessionLocal, Producto, Conversacion, init_db

# Inicializar DB (crea tablas si no existen)
init_db()

app = FastAPI(title="Bot de Ventas — Conversacional")

# --- ENV (poner en Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")              # token bot ventas
BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")              # API key del LLM (OpenAI u otro)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")   # deja valor por defecto, se puede cambiar
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")                # token que usa bot investigador para update_products
PUBLIC_URL = os.getenv("PUBLIC_URL", "")                  # ej: https://auto-sales-bot.onrender.com

# --- util: enviar mensaje sync/async a Telegram
async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    if not BASE_TELEGRAM_URL:
        return None
    url = f"{BASE_TELEGRAM_URL}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
            return r.json()
        except Exception:
            return None

# --- util: preparar contexto corto con productos (top N)
def productos_contexto(limit: int = 6) -> str:
    db = SessionLocal()
    try:
        prods = db.query(Producto).filter(Producto.activo == True).order_by(Producto.created_at.desc()).limit(limit).all()
    finally:
        db.close()
    if not prods:
        return "No hay productos en catálogo actualmente."
    lines = []
    for p in prods:
        lines.append(f"{p.id}. {p.nombre} — {p.precio} {p.moneda} — { (p.descripcion[:120] + '...') if p.descripcion and len(p.descripcion)>120 else (p.descripcion or '') } Link:{p.link or '—'}")
    return "\n".join(lines)

# --- llamador al LLM (OpenAI style)
async def llm_generate_reply(user_text: str, chat_id: int, max_products: int = 6) -> str:
    if not OPENAI_API_KEY:
        # fallback simple si no hay API: respuestas basicas locales
        # intenta responder con plantilla basada en DB:
        if user_text.strip().isdigit():
            pid = int(user_text.strip())
            db = SessionLocal()
            try:
                p = db.query(Producto).filter(Producto.id == pid).first()
            finally:
                db.close()
            if p:
                return f"✅ {p.nombre}\n{p.descripcion or ''}\nPrecio: {p.precio} {p.moneda}\nCompra: {p.link or '—'}"
            return "No encontré ese producto. Escribe 'productos' para ver el catálogo."
        if "producto" in user_text.lower() or "productos" in user_text.lower():
            return "Puedo mostrarte el catálogo. Escribe 'productos' para ver la lista."
        return "Hola — dime qué necesitas o escribe 'productos' para ver el catálogo."

    # preparar prompt con instrucciones de venta (multilingüe, tono profesional, no slang)
    system_prompt = (
        "Eres un asistente de ventas profesional. Responde como un agente humano: educado, persuasivo, "
        "multilingüe (responde en el idioma del usuario). Usa la información del catálogo provista. "
        "No uses jerga grosera ni modismos locales ofensivos. Si el usuario pide 'productos' muestra una lista breve. "
        "Si el usuario escribe un número, devuelve el detalle del producto correspondiente. "
        "Si no estás seguro, pregunta aclaraciones y ofrece mostrar el catálogo."
    )

    product_ctx = productos_contexto(limit=max_products)

    user_prompt = (
        f"CATÁLOGO (contexto):\n{product_ctx}\n\n"
        f"USUARIO: {user_text}\n\n"
        "RESPONDE como vendedor de forma natural, breve y clara."
    )

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.9
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code != 200:
            # devolver fallback
            return "Lo siento, hay un problema con la IA en este momento. ¿Quieres que te muestre el catálogo?"
        j = r.json()
    # extraer respuesta
    try:
        answer = j["choices"][0]["message"]["content"].strip()
    except Exception:
        answer = "Lo siento, no pude generar respuesta ahora."
    # guardar en tabla conversacion (contexto simple)
    db = SessionLocal()
    try:
        conv = db.query(Conversacion).filter(Conversacion.chat_id == chat_id).first()
        if not conv:
            conv = Conversacion(chat_id=chat_id, contexto=user_text, updated_at=datetime.utcnow())
            db.add(conv)
        else:
            conv.contexto = (conv.contexto or "") + "\nUSER: " + user_text[:400]
            conv.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    return answer

# --- endpoint webhook (Telegram POST)
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(content={"ok": False, "error": "invalid JSON"}, status_code=400)

    if "message" not in update:
        return JSONResponse(content={"ok": True})

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    if not text:
        await send_message(chat_id, "Solo proceso texto por ahora.")
        return JSONResponse(content={"ok": True})

    # comandos directos rápidos
    lower = text.lower()
    if lower == "/start":
        await send_message(chat_id, "🤖 Hola — soy tu asistente de ventas. Dime qué buscas o escribe 'productos'.")
        return JSONResponse(content={"ok": True})

    if lower in ("/productos", "productos", "catalogo", "catálogo"):
        # mostrar listado directo desde DB (rápido)
        db = SessionLocal()
        try:
            prods = db.query(Producto).filter(Producto.activo == True).order_by(Producto.created_at.desc()).limit(20).all()
        finally:
            db.close()
        if not prods:
            await send_message(chat_id, "Ahora mismo no hay productos en catálogo.")
            return JSONResponse(content={"ok": True})
        lista = "\n".join([f"{p.id}. {p.nombre} — {p.precio} {p.moneda}" for p in prods])
        await send_message(chat_id, f"📦 Catálogo:\n\n{lista}\n\nEscribe el número para ver detalles.")
        return JSONResponse(content={"ok": True})

    # si usuario envía solo un número -> entregar detalle sin LLM (rápido)
    if text.isdigit():
        pid = int(text)
        db = SessionLocal()
        try:
            p = db.query(Producto).filter(Producto.id == pid).first()
        finally:
            db.close()
        if p:
            desc = p.descripcion or ""
            link = p.link or "—"
            await send_message(chat_id, f"✅ *{p.nombre}*\n{desc}\nPrecio: {p.precio} {p.moneda}\nCompra: {link}")
            return JSONResponse(content={"ok": True})
        else:
            await send_message(chat_id, "No encontré ese producto. Escribe 'productos' para ver la lista.")
            return JSONResponse(content={"ok": True})

    # caso general: delegar a LLM (con contexto productos)
    respuesta = await llm_generate_reply(text, chat_id, max_products=6)
    await send_message(chat_id, respuesta)
    return JSONResponse(content={"ok": True})

# --- endpoint admin para actualizar catálogo (bot investigador llama con header x-admin-token)
@app.post("/admin/update_products")
async def admin_update_products(request: Request, x_admin_token: Optional[str] = Header(None)):
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
                pid = None
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

# set_webhook helper (opcional)
@app.get("/set_webhook")
async def set_webhook():
    if not PUBLIC_URL or not TELEGRAM_TOKEN:
        raise HTTPException(status_code=400, detail="PUBLIC_URL o TELEGRAM_TOKEN faltan")
    webhook_url = f"{PUBLIC_URL}/webhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook", data={"url": webhook_url})
        return JSONResponse(content=resp.json())

@app.get("/")
def root():
    return {"message": "🤖 Bot de Ventas funcionando en Render 🚀"}
