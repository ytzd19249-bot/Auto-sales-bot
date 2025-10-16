# main.py
import os
import re
import httpx
import openai
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

from sqlalchemy.orm import Session
from sqlalchemy import and_

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import SessionLocal, Producto, init_db

# =========================
# App + Scheduler
# =========================
scheduler = AsyncIOScheduler()

# =========================
# INIT DB
# =========================
init_db()

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")   # token del bot de Telegram
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # opcional
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")    # token que usa el investigador/checkout
PUBLIC_URL  = os.getenv("PUBLIC_URL", "")     # ej: https://auto-sales-bot.onrender.com
BASE_TELEGRAM = f"https://api.telegram.org/bot{BOT_TOKEN}"

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# =========================
# Utils
# =========================
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

def normalize_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())

# =========================
# Lógica conversacional
# =========================
async def handle_user_message(chat_id: int, text: str, db: Session):
    t = normalize_text(text)

    # SALUDOS
    if re.search(r"\b(hola|buenas|buenos días|buenas tardes|buenas noches|hey)\b", t):
        return await send_message(chat_id, "👋 ¡Hola! Soy tu asistente de ventas. ¿En qué te ayudo hoy?")

    # CATÁLOGO
    if re.search(r"\b(producto|productos|catálogo|catalogo|qué tienen|qué venden|tienen)\b", t):
        productos = db.query(Producto).filter(Producto.activo == True).order_by(Producto.created_at.desc()).limit(50).all()
        if not productos:
            return await send_message(chat_id, "📭 Por ahora no hay productos disponibles. El catálogo se actualiza automáticamente.")
        lines = [f"{p.id}. {p.nombre} — {p.precio} {p.moneda}" for p in productos]
        text_out = "🛍️ Productos disponibles:\n\n" + "\n".join(lines[:20]) + "\n\nEscribe el número del producto para ver detalles."
        return await send_message(chat_id, text_out)

    # DETALLE POR ID
    m = re.match(r"^(\d+)$", t)
    if m:
        pid = int(m.group(1))
        prod = db.query(Producto).filter(Producto.id == pid).first()
        if not prod:
            return await send_message(chat_id, "❌ No encontré ese producto. Escribí 'productos' para ver la lista.")
        if not prod.activo:
            return await send_message(chat_id, f"🚫 {prod.nombre} no está disponible.")
        detail = (
            f"✅ *{prod.nombre}*\n"
            f"{prod.descripcion or 'Sin descripción.'}\n"
            f"Precio: {prod.precio} {prod.moneda}\n"
            f"Compra: {prod.link or 'Enlace no disponible.'}"
        )
        return await send_message(chat_id, detail)

    # IA opcional
    if OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un vendedor amable, claro y profesional. Responde como una persona en el idioma del usuario. Si es pregunta sobre un producto, pide el id o muestra catálogo."},
                    {"role": "user", "content": text}
                ],
                max_tokens=400,
                temperature=0.6,
            )
            answer = resp["choices"][0]["message"]["content"]
            return await send_message(chat_id, answer)
        except Exception:
            await send_message(chat_id, "⚠️ Error en IA. Te respondo rápidamente: " + (text[:300] if text else ""))
            return

    # Fallback
    return await send_message(chat_id, f"🤖 Recibí tu mensaje: {text}\n(Escribe 'productos' para ver el catálogo.)")

# =========================
# Webhook de Telegram
# =========================
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

# =========================
# Admin: upsert de productos (desde Investigador)
# =========================
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
            # busca por link (preferido) o id/nombre
            link = v.get("link")
            prod = None
            if link:
                prod = db.query(Producto).filter(Producto.link == link).first()
            if not prod:
                try:
                    pid = int(k)
                    prod = db.query(Producto).filter(Producto.id == pid).first()
                except:
                    prod = None

            if prod:
                prod.nombre = v.get("nombre", prod.nombre)
                prod.descripcion = v.get("descripcion", prod.descripcion)
                try:
                    prod.precio = float(v.get("precio", prod.precio or 0))
                except:
                    pass
                prod.moneda = v.get("moneda", prod.moneda or "USD")
                prod.link = link or prod.link
                prod.source = v.get("source", prod.source or "investigador")
                prod.activo = bool(v.get("activo", True))
            else:
                new = Producto(
                    nombre=v.get("nombre", "Sin nombre"),
                    descripcion=v.get("descripcion", ""),
                    precio=float(v.get("precio", 0) or 0),
                    moneda=v.get("moneda", "USD"),
                    link=link,
                    source=v.get("source", "investigador"),
                    activo=bool(v.get("activo", True)),
                )
                db.add(new)
            updated.append(k)
        db.commit()
    finally:
        db.close()
    return {"ok": True, "updated": updated}

# =========================
# Admin: sync masivo (solo upsert, NO desactiva por ausencia)
# =========================
@app.post("/admin/sync_products")
async def admin_sync_products(request: Request):
    token = request.headers.get("x-admin-token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = await request.json()
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Invalid body: items[] required")

    db = SessionLocal()
    try:
        upserted = 0
        for v in items:
            link = v.get("link")
            nombre = v.get("nombre", "Sin nombre")
            q = db.query(Producto)
            prod = q.filter(Producto.link == link).first() if link else q.filter(Producto.nombre == nombre).first()
            if prod:
                prod.nombre = nombre or prod.nombre
                prod.descripcion = v.get("descripcion", prod.descripcion)
                try:
                    prod.precio = float(v.get("precio", prod.precio or 0))
                except:
                    pass
                prod.moneda = v.get("moneda", prod.moneda or "USD")
                if link: prod.link = link
                prod.source = v.get("source", prod.source or "investigador")
                prod.activo = bool(v.get("activo", True))
            else:
                nuevo = Producto(
                    nombre=nombre,
                    descripcion=v.get("descripcion", ""),
                    precio=float(v.get("precio", 0) or 0),
                    moneda=v.get("moneda", "USD"),
                    link=link,
                    source=v.get("source", "investigador"),
                    activo=bool(v.get("activo", True)),
                )
                db.add(nuevo)
            upserted += 1
        db.commit()
        return {"ok": True, "upserted": upserted}
    finally:
        db.close()

# =========================
# Admin: registrar venta (reactiva y marca fecha)
# =========================
@app.post("/admin/record_sale")
async def admin_record_sale(request: Request):
    token = request.headers.get("x-admin-token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    pid = int(body.get("product_id", 0))
    if not pid:
        raise HTTPException(status_code=400, detail="product_id requerido")

    db = SessionLocal()
    try:
        p = db.query(Producto).filter(Producto.id == pid).first()
        if not p:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        p.ventas_total = (p.ventas_total or 0) + 1
        p.ultima_venta_at = datetime.utcnow()
        p.activo = True  # si estaba inactivo, lo reactiva
        db.commit()
