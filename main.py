from fastapi import FastAPI, Request
import requests, os
from db import SessionLocal, Producto

TOKEN = os.getenv("BOT_VENTAS_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text.lower() == "/start":
            send_message(chat_id, "¡Bienvenido al Bot de Ventas! Escriba /catalogo para ver los productos.")
        
        elif text.lower() == "/catalogo":
            db = SessionLocal()
            productos = db.query(Producto).all()
            if not productos:
                send_message(chat_id, "No hay productos disponibles por ahora.")
            else:
                for p in productos:
                    send_message(chat_id, f"{p.nombre} - ${p.precio}\n{p.descripcion}")
            db.close()

        elif text.lower().startswith("/investigar"):
            # Mandar consulta al bot de investigación
            query = text.replace("/investigar", "").strip()
            send_message(chat_id, f"Derivando consulta al bot de investigación: {query}")
            # Aquí se puede hacer un requests.post al webhook del bot de investigación si queremos conexión directa

        else:
            send_message(chat_id, "Comando no reconocido. Use /catalogo o /investigar <tema>.")
    
    return {"ok": True}
