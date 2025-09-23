from fastapi import FastAPI, Request
import httpx
from db import SessionLocal, Producto

app = FastAPI()

# Función para enviar mensajes a Telegram
async def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )


@app.get("/")
async def root():
    return {"message": "🤖 Bot de Ventas funcionando en Render 🚀"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Apertura de sesión DB
    db = SessionLocal()

    try:
        # Si el usuario saluda
        if text.lower() in ["hola", "hi", "hello", "buenos días", "buenas", "hey"]:
            await send_message(
                os.getenv("TELEGRAM_TOKEN"),
                chat_id,
                "👋 ¡Hola! Soy tu asesor virtual de ventas. Pregúntame por cualquier producto o escribe *ver productos*."
            )
            return {"ok": True}

        # Mostrar productos
        if text.lower() in ["productos", "ver productos", "/productos"]:
            productos = db.query(Producto).filter(Producto.activo == True).all()
            if not productos:
                await send_message(
                    os.getenv("TELEGRAM_TOKEN"),
                    chat_id,
                    "🚫 No hay productos disponibles en este momento."
                )
            else:
                lista = "\n".join(
                    [f"{p.id}. {p.titulo} - {p.precio} {p.moneda}" for p in productos]
                )
                await send_message(
                    os.getenv("TELEGRAM_TOKEN"),
                    chat_id,
                    f"🛍️ *Lista de productos disponibles:*\n{lista}\n👉 Escribe el número del producto para más info."
                )
            return {"ok": True}

        # Si escribe un número de producto
        if text.isdigit():
            producto = db.query(Producto).filter(Producto.id == int(text)).first()
            if producto:
                if producto.activo:
                    msg = f"✅ {producto.titulo} cuesta {producto.precio} {producto.moneda}.\nCompra aquí 👉 {producto.link}"
                else:
                    msg = f"🚫 El producto *{producto.titulo}* ya no está disponible."
                await send_message(os.getenv("TELEGRAM_TOKEN"), chat_id, msg)
            else:
                await send_message(
                    os.getenv("TELEGRAM_TOKEN"),
                    chat_id,
                    "❓ Producto no encontrado. Escribe *ver productos* para revisar el catálogo."
                )
            return {"ok": True}

        # Respuesta general (para conversación más humana)
        await send_message(
            os.getenv("TELEGRAM_TOKEN"),
            chat_id,
            f"🤝 Gracias por tu mensaje: *{text}*. Si deseas ver opciones disponibles, escribe *ver productos*."
        )
        return {"ok": True}

    finally:
        db.close()
