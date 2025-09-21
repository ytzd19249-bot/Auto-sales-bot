# main.py
import os
import requests
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # <-- setear en Render (Settings -> Env Vars)
if not TELEGRAM_TOKEN:
    raise RuntimeError("Falta TELEGRAM_TOKEN en las variables de entorno")

BASE_TELEGRAM = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # opcional, ver más abajo

app = FastAPI()

# --- Catálogo simple (ejemplo) ---
PRODUCTS = {
    "1": {"name": "Curso Básico", "price": "15.00", "currency": "USD", "buy": "https://tu-pago/curso-basico"},
    "2": {"name": "Plantilla Funnel", "price": "29.00", "currency": "USD", "buy": "https://tu-pago/plantilla"},
    "3": {"name": "Consultoría 30m", "price": "49.00", "currency": "USD", "buy": "https://tu-pago/consultoria"},
}

# Util — enviar mensaje simple a telegram
def send_message(chat_id: int, text: str, reply_markup: dict = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(f"{BASE_TELEGRAM}/sendMessage", json=payload, timeout=10)
    try:
        resp.raise_for_status()
    except Exception:
        # opcional: loguear resp.text
        pass
    return resp.json()

# Manejo de comandos / lógica
def handle_update(update: dict):
    # update viene directamente de Telegram webhook
    if "message" not in update:
        return
    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    # Comandos básicos
    if text.startswith("/start"):
        send_message(chat_id, "Hola 👋 soy tu Bot de Ventas. Usa /productos para ver lo que ofrezco.")
        return

    if text.startswith("/productos") or text.lower().strip() == "productos":
        lines = ["Productos disponibles:"]
        for pid, p in PRODUCTS.items():
            lines.append(f"{pid}. {p['name']} — {p['price']} {p['currency']}")
        lines.append("\nEnvía /comprar <id> para recibir el link de pago.")
        send_message(chat_id, "\n".join(lines))
        return

    if text.startswith("/comprar"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "Formato: /comprar <id>. Ejemplo: /comprar 1")
            return
        pid = parts[1].strip()
        p = PRODUCTS.get(pid)
        if not p:
            send_message(chat_id, f"No encontré el producto {pid}. Usa /productos para ver ids válidos.")
            return
        # Responder con link de pago
        text_reply = f"Has elegido <b>{p['name']}</b>\nPrecio: {p['price']} {p['currency']}\nPagar aquí: {p['buy']}"
        # Opcional: enviar botón (inline keyboard)
        reply_markup = {
            "inline_keyboard": [[{"text": "Pagar ahora", "url": p["buy"]}]]
        }
        send_message(chat_id, text_reply, reply_markup=reply_markup)
        return

    # Respuesta por defecto (FAQ / fallback)
    send_message(chat_id, "No entendí tu mensaje. Prueba /productos o /comprar <id>.")

# Webhook endpoint que Telegram va a llamar (POST)
@app.post("/telegram/{token}")
async def telegram_webhook(token: str, request: Request, background_tasks: BackgroundTasks):
    # seguridad: token en URL (debe ser igual a TELEGRAM_TOKEN o usar WEBHOOK_SECRET)
    # permitimos que token sea el token completo o un secreto personalizado
    if token != TELEGRAM_TOKEN and (WEBHOOK_SECRET and token != WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")

    update = await request.json()
    # manejar en background para devolver 200 rápido a Telegram
    background_tasks.add_task(handle_update, update)
    return {"ok": True}

# helper opcional para setear webhook desde el navegador (protegido)
@app.get("/set_webhook")
def set_webhook():
    # Compose webhook URL: https://TU_DOMAIN/telegram/<token_o_secreto>
    domain = os.environ.get("PUBLIC_URL")  # setear PUBLIC_URL en Render con tu dominio (ej: https://auto-sales-bot.onrender.com)
    if not domain:
        raise HTTPException(status_code=400, detail="Set PUBLIC_URL env var")
    webhook_url = f"{domain}/telegram/{TELEGRAM_TOKEN}"
    resp = requests.post(f"{BASE_TELEGRAM}/setWebhook", data={"url": webhook_url}, timeout=10)
    return resp.json()
