from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", TELEGRAM_TOKEN)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Lista de productos
PRODUCTOS = [
    {"id": 1, "nombre": "Laptop Ultra", "precio": 900, "link_pago": "https://pago.com/laptop"},
    {"id": 2, "nombre": "Celular Pro", "precio": 500, "link_pago": "https://pago.com/celular"},
    {"id": 3, "nombre": "Auriculares X", "precio": 150, "link_pago": "https://pago.com/auriculares"},
]

@app.get("/")
async def home():
    return {"message": "Bot de Ventas en Render funcionando 🚀"}

@app.get("/set_webhook")
async def set_webhook():
    url = f"{PUBLIC_URL}/telegram/{WEBHOOK_SECRET}"
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/setWebhook?url={url}")
    return r.json()

@app.post(f"/telegram/{{token}}")
async def telegram_webhook(token: str, request: Request):
    if token != WEBHOOK_SECRET:
        return {"error": "Unauthorized"}

    data = await request.json()

    # Si es un mensaje de texto normal
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").strip().lower().replace(" ", "")

        if text in ["/start", "start"]:
            await send_message(chat_id, "👋 Hola, soy tu Bot de Ventas. Usa /productos para ver lo que ofrezco.")
        elif text in ["/productos", "productos"]:
            await mostrar_productos(chat_id)
        elif text.isdigit():  # Si el usuario responde con un número
            num = int(text)
            producto = next((p for p in PRODUCTOS if p["id"] == num), None)
            if producto:
                await confirmar_compra(chat_id, producto)
            else:
                await send_message(chat_id, "❌ Número inválido. Usa /productos para ver la lista.")
        else:
            await send_message(chat_id, "🤖 No entiendo ese comando. Usa /productos.")

    # Si es un callback (cuando aprieta un botón)
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        data_cb = cq["data"]

        if data_cb.startswith("comprar_"):
            prod_id = int(data_cb.split("_")[1])
            producto = next((p for p in PRODUCTOS if p["id"] == prod_id), None)
            if producto:
                await send_message(chat_id, f"✅ Aquí está tu link de pago: {producto['link_pago']}")
        elif data_cb == "cancelar":
            await send_message(chat_id, "❌ Compra cancelada.")

    return {"ok": True}

# ================= FUNCIONES ===================

async def send_message(chat_id, text, reply_markup=None):
    async with httpx.AsyncClient() as client:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await client.post(f"{BASE_URL}/sendMessage", json=payload)

async def mostrar_productos(chat_id):
    texto = "🛍️ *Lista de productos:*\n\n"
    for p in PRODUCTOS:
        texto += f"{p['id']}. {p['nombre']} - ${p['precio']}\n"
    texto += "\n👉 Responde con el número del producto para comprarlo."

    await send_message(chat_id, texto)

async def confirmar_compra(chat_id, producto):
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Sí", "callback_data": f"comprar_{producto['id']}"},
                {"text": "❌ No", "callback_data": "cancelar"}
            ]
        ]
    }
    await send_message(chat_id, f"¿Quieres comprar *{producto['nombre']}* por ${producto['precio']}?", reply_markup=markup)
