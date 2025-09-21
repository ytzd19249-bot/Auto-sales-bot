# main.py
import os
import json
from typing import List, Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
import httpx
from pathlib import Path

# -------- CONFIG --------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("Falta TELEGRAM_TOKEN en variables de entorno")

PUBLIC_URL = os.environ.get("PUBLIC_URL")  # https://auto-sales-bot.onrender.com
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", TELEGRAM_TOKEN)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")  # Se usa para proteger endpoints de actualización

BASE_TELEGRAM = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

DATA_FILE = Path("products.json")  # archivo local (útil para pruebas); en prod usar DB

app = FastAPI(title="Bot de Ventas - CompraFácil")

# -------- Helpers para productos (fuente dinámica) --------
def load_products() -> Dict[str, Dict[str, Any]]:
    """Carga productos desde products.json en forma {id: {...}}"""
    if not DATA_FILE.exists():
        return {}
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        # aseguramos que keys sean strings
        return {str(k): v for k, v in raw.items()}
    except Exception:
        return {}

def save_products(products: Dict[str, Dict[str, Any]]):
    DATA_FILE.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")

# Inicializa archivo si no existe (ejemplo vacío)
if not DATA_FILE.exists():
    sample = {
        "1": {"title": "Ejemplo: Producto A", "price": "100", "currency": "USD", "source": "Amazon", "link": "https://example.com/1"},
        "2": {"title": "Ejemplo: Producto B", "price": "50",  "currency": "USD", "source": "Hotmart", "link": "https://example.com/2"}
    }
    save_products(sample)

# -------- Telegram utils (async) --------
async def tg_send_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "Markdown"):
    async with httpx.AsyncClient(timeout=10) as client:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = await client.post(f"{BASE_TELEGRAM}/sendMessage", json=payload)
        return resp.json()

# -------- Lógica de negocio --------
def normalize_text(s: str) -> str:
    return s.strip().lower()

async def handle_update_async(update: dict):
    # llamada en background
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        text_norm = normalize_text(text)

        # /start
        if text_norm.startswith("/start") or "hola" in text_norm:
            await tg_send_message(chat_id, "👋 *Hola!* Soy *CompraFácil Bot*. Usa `/productos` para ver lo que hay hoy.")
            return

        # /productos o consultas por palabra clave
        if text_norm.startswith("/productos") or "producto" in text_norm or "catalogo" in text_norm or text_norm == "productos":
            products = load_products()
            if not products:
                await tg_send_message(chat_id, "Lo siento, ahora mismo no hay productos disponibles. Vuelve en breve.")
                return
            lines = ["🛍️ *Lista de productos disponibles:*"]
            for pid, p in products.items():
                lines.append(f"{pid}. {p.get('title')} - ${p.get('price')} ({p.get('source')})")
            lines.append("\n👉 Responde con el número del producto para ver opciones de compra.")
            await tg_send_message(chat_id, "\n".join(lines))
            return

        # /comprar <id>
        if text_norm.startswith("/comprar"):
            parts = text_norm.split()
            if len(parts) < 2:
                await tg_send_message(chat_id, "Formato: `/comprar <id>` — ejemplo: `/comprar 1`")
                return
            pid = parts[1]
            products = load_products()
            p = products.get(pid)
            if not p:
                await tg_send_message(chat_id, f"No encontré el producto `{pid}`. Usa `/productos` para ver IDs válidos.")
                return
            # ofrecer opciones: PayPal + SINPE placeholder + abrir WhatsApp
            pay_text = f"Has elegido *{p.get('title')}* — ${p.get('price')} ({p.get('source')})\n\nElige método de pago:"
            buttons = [
                [{"text": "💳 PayPal", "url": p.get("link") or p.get("paypal_link") or ""}],
                [{"text": "📲 SINPE (Instrucciones)", "callback_data": f"sinpe_{pid}"}],
                [{"text": "💬 WhatsApp", "url": f"https://wa.me/506TU_NUMERO?text=Hola%20quiero%20comprar%20{pid}"}]
            ]
            reply_markup = {"inline_keyboard": buttons}
            await tg_send_message(chat_id, pay_text, reply_markup=reply_markup, parse_mode="Markdown")
            return

        # si el usuario escribe sólo un número (ej: "2")
        if text_norm.isdigit():
            products = load_products()
            p = products.get(text_norm)
            if p:
                # igual que /comprar
                pay_text = f"Has elegido *{p.get('title')}* — ${p.get('price')} ({p.get('source')})\n\nElige método de pago:"
                buttons = [
                    [{"text": "💳 PayPal", "url": p.get("link") or p.get("paypal_link") or ""}],
                    [{"text": "📲 SINPE (Instrucciones)", "callback_data": f"sinpe_{text_norm}"}],
                    [{"text": "💬 WhatsApp", "url": f"https://wa.me/506TU_NUMERO?text=Hola%20quiero%20comprar%20{text_norm}"}]
                ]
                reply_markup = {"inline_keyboard": buttons}
                await tg_send_message(chat_id, pay_text, reply_markup=reply_markup, parse_mode="Markdown")
                return

        # fallback
        await tg_send_message(chat_id, "No entendí eso 🤔. Usa `/productos` o responde con el número del producto.")

    # callback_query (botones inline)
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        chat_id = cq["message"]["chat"]["id"]
        # SINPE placeholder: damos instrucciones
        if data.startswith("sinpe_"):
            pid = data.split("_", 1)[1]
            products = load_products()
            p = products.get(pid)
            if not p:
                await tg_send_message(chat_id, "Producto no encontrado.")
                return
            sinpe_text = (
                f"📲 *Pago SINPE Móvil*\n\n"
                f"Producto: *{p.get('title')}*\n"
                f"Monto: *${p.get('price')}*\n\n"
                f"Transfiere a: *Tu Nombre / Empresa*\n"
                f"Número SINPE: *8XXXXXXX*\n\n"
                "Cuando hagas la transferencia, envía aquí el comprobante y te confirmamos la orden."
            )
            await tg_send_message(chat_id, sinpe_text)
            return

# -------- Endpoints publicos / webhooks --------
@app.post("/telegram/{token}")
async def telegram_webhook(token: str, request: Request, background_tasks: BackgroundTasks):
    # seguridad: permitimos que token sea TELEGRAM_TOKEN o WEBHOOK_SECRET
    if token != TELEGRAM_TOKEN and token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    update = await request.json()
    # log simple - aparecerá en los logs de Render
    print("UPDATE RECIBIDO:", update)
    background_tasks.add_task(handle_update_async, update)
    return {"ok": True}

@app.get("/set_webhook")
async def set_webhook():
    if not PUBLIC_URL:
        raise HTTPException(status_code=400, detail="Set PUBLIC_URL env var")
    url = f"{PUBLIC_URL}/telegram/{WEBHOOK_SECRET}"
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_TELEGRAM}/setWebhook", params={"url": url})
    return r.json()

# -------- API para que Bot Investigador actualice productos (PROTEGIDO) --------
# El investigador o un script puede enviar JSON con la estructura { "id": {...}, ... }
@app.post("/admin/update_products")
async def admin_update_products(request: Request, x_admin_token: str = Header(None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    # Guardamos directamente (sobrescribe)
    save_products({str(k): v for k, v in data.items()})
    return {"ok": True, "saved": len(data)}

@app.post("/admin/add_product")
async def admin_add_product(request: Request, x_admin_token: str = Header(None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    # body esperado: {"id": "5", "title": "...", "price":"...", "link":"...", "source":"Amazon"}
    prod_id = str(body.get("id") or body.get("product_id"))
    if not prod_id:
        raise HTTPException(status_code=400, detail="Missing id")
    products = load_products()
    products[prod_id] = {
        "title": body.get("title", ""),
        "price": str(body.get("price", "")),
        "currency": body.get("currency", "USD"),
        "link": body.get("link", ""),
        "source": body.get("source", "")
    }
    save_products(products)
    return {"ok": True, "id": prod_id}

# Endpoint público para ver productos (puede usarlo Bot Investigador o frontend)
@app.get("/products")
def get_products():
    return load_products()

# Root
@app.get("/")
def root():
    return {"message": "Bot de Ventas - CompraFácil (alive)"}
