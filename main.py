import os
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
import httpx

# --- CONFIGURACIÓN GENERAL ---
logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Bot de Ventas")

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "ventas_admin_12345")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# --- MODELO PRODUCTOS ---
class Producto(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Crear tabla si no existe
Base.metadata.create_all(bind=engine)

# --- AUTORIZACIÓN ---
def check_token(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta Bearer token")
    token = authorization.replace("Bearer ", "").strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")
    return True

# --- ENDPOINT para recibir producto desde el bot investigador ---
class ProductoIn(BaseModel):
    nombre: str

@app.post("/api/ventas/recibir-producto", dependencies=[Depends(check_token)])
def recibir_producto(payload: ProductoIn):
    db = SessionLocal()
    try:
        db.execute(text("INSERT INTO productos (nombre) VALUES (:nombre)"), {"nombre": payload.nombre})
        db.commit()
        return {"ok": True, "msg": f"Producto '{payload.nombre}' guardado correctamente."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# --- ENDPOINT para listar productos (para probar en el navegador) ---
@app.get("/productos")
def listar_productos():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT id, nombre, created_at FROM productos ORDER BY created_at DESC"))
        productos = [dict(row._mapping) for row in result]
        return {"productos": productos}
    finally:
        db.close()

# --- WEBHOOK DE TELEGRAM ---
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logging.info(f"📩 Mensaje recibido: {data}")

    # Si el mensaje viene de Telegram
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").lower()

        if "producto" in text or "catálogo" in text or "catalogo" in text:
            db = SessionLocal()
            result = db.execute(text("SELECT nombre, created_at FROM productos ORDER BY created_at DESC LIMIT 5"))
            productos = [dict(row._mapping) for row in result]
            db.close()

            if not productos:
                reply = "📦 Por ahora no hay productos disponibles. El catálogo se actualiza automáticamente."
            else:
                reply = "🛍️ Productos disponibles:\n"
                for p in productos:
                    reply += f"• {p['nombre']} (📅 {p['created_at'].strftime('%Y-%m-%d')})\n"

        elif "/start" in text:
            reply = "👋 ¡Hola! Soy tu asistente de ventas. Podés pedirme 'productos' o 'catálogo' para ver lo disponible."
        else:
            reply = "💬 No entendí. Podés escribir 'productos' para ver el catálogo."

        # Enviar respuesta a Telegram
        bot_token = os.getenv("BOT_TOKEN", "8255571596:AAEvqpVQR__FYQUerAVZtEWXNWu1ZtHT3r8")
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": reply}
            )

    return {"ok": True}

# --- ROOT SIMPLE PARA COMPROBAR QUE ESTÁ ACTIVO ---
@app.get("/")
def root():
    return {"status": "Bot de ventas activo 🚀"}
