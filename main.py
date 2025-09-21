from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
import os

app = FastAPI()

# Token de admin (para que solo el bot investigador pueda actualizar)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "miclaveadmin")

# Catálogo en memoria (puedes cambiarlo a base de datos luego)
PRODUCTS = {}

@app.get("/")
async def root():
    return {"message": "Bot de Ventas en Render funcionando 🚀"}

@app.post("/telegram/{token}")
async def telegram_webhook(token: str, request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "").strip().lower()

    # Respuesta a /start
    if text == "/start":
        return await send_message(token, chat_id, "👋 Hola! Soy tu bot de ventas. Escribe /productos para ver lo que tengo disponible.")

    # Respuesta a /productos
    if text == "/productos":
        active_products = [f"{pid}. {info['title']} - {info['price']} {info['currency']}" 
                           for pid, info in PRODUCTS.items() if info.get("active", True)]
        if not active_products:
            return await send_message(token, chat_id, "🚫 No hay productos disponibles por ahora.")
        product_list = "\n".join(active_products)
        return await send_message(token, chat_id, f"🛍️ *Lista de productos:*\n{product_list}\n👉 Responde con el número del producto para comprarlo.")

    # Responder si el usuario escribe un número de producto
    if text.isdigit():
        pid = text
        product = PRODUCTS.get(pid)
        if product:
            if product.get("active", True):
                msg = f"✅ {product['title']} cuesta {product['price']} {product['currency']}.\nCompra aquí 👉 {product['link']}"
            else:
                msg = f"🚫 Lo siento, el producto *{product['title']}* ya no está disponible.\n¿Quieres ver alternativas? Escribe /productos"
            return await send_message(token, chat_id, msg)
        else:
            return await send_message(token, chat_id, "❓ Producto no encontrado. Escribe /productos para ver lo disponible.")

    return {"ok": True}

# Endpoint de admin para actualizar/agregar productos
@app.post("/admin/update_products")
async def update_products(request: Request, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    data = await request.json()
    for pid, info in data.items():
        if pid in PRODUCTS:
            PRODUCTS[pid].update(info)  # actualizar si ya existe
        else:
            PRODUCTS[pid] = info        # agregar si es nuevo
        if "active" not in PRODUCTS[pid]:
            PRODUCTS[pid]["active"] = True  # por defecto activo

    return {"ok": True, "updated": list(data.keys()), "total_products": len(PRODUCTS)}

# Función para enviar mensajes a Telegram
import httpx
async def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    return {"ok": True}
