import os
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, func, text as sql_text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
import httpx

# --- CONFIGURACIÓN GENERAL ---
logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Bot de Ventas")

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "ventas_admin_12345")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8255571596:AAEvqpVQR__FYQUerAVZtEWXNWu1ZtHT3r8")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# --- MODELO PRODUCTOS ---
class Producto(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    precio = Column(Numeric(12, 2), nullable=True)
    moneda = Column(String, default="USD")
    enlace = Column(String, nullable=True)
    imagen_url = Column(String, nullable=True)
    fuente = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

Base.metadata.create_all(bind=engine)

# --- AUTORIZACIÓN ---
def check_token(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta Bearer token")
    token = authorization.replace("Bearer ", "").strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")
    return True

# --- ESQUEMA PARA RECIBIR PRODUCTOS DEL BOT INVESTIGADOR ---
class ProductoIn(BaseModel):
    nombre: str
    precio: float | None = None
    moneda: str | None = "USD"
    enlace: str | None = None
    imagen_url: str | None = None
    fuente: str | None = None

# --- ENDPOINT PARA RECIBIR PRODUCTO DESDE EL BOT INVESTIGADOR ---
@app.post("/api/ventas/recibir-producto", dependencies=[Depends(check_token)])
def recibir_producto(payload: ProductoIn):
    db = SessionLocal()
    try:
        db.execute(
            sql_text("""
                INSERT INTO productos (nombre, precio, moneda, enlace, imagen_url, fuente)
                VALUES (:nombre, :precio, :moneda, :enlace, :imagen_url, :fuente)
            """),
            {
                "nombre": payload.nombre,
                "precio": payload.precio,
                "moneda": payload.moneda,
                "enlace": payload.enlace,
                "imagen_url": payload.imagen_url,
                "fuente": payload.fuente
            },
        )
        db.commit()
        return {"ok": True, "msg": f"Producto '{payload.nombre}' guardado correctamente."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# --- ENDPOINT PARA LISTAR PRODUCTOS (para ver en el navegador) ---
@app.get("/productos")
def listar_productos():
    db = SessionLocal()
    try:
        result = db.execute(sql_text("SELECT * FROM productos ORDER BY created_at DESC LIMIT 10"))
        productos = [dict(row._mapping) for row in result]
        return {"productos": productos}
    finally:
        db.close()

# --- WEBHOOK TELEGRAM ---
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logging.info(f"📩 Mensaje recibido: {data}")

    if "message" not in data:
        return {"ok": True}

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "").lower()

    # --- CONSULTAR PRODUCTOS EN LA BASE ---
    db = SessionLocal()
    result = db.execute(sql_text("SELECT nombre, precio, moneda, enlace, imagen_url, fuente, created_at FROM productos ORDER BY created_at DESC LIMIT 5"))
    productos = [dict(row._mapping) for row in result]
    db.close()

    # --- RESPUESTAS SEGÚN TEXTO ---
    if "/start" in text:
        reply = "👋 ¡Hola! Soy tu asistente de ventas. Escribí 'productos' o 'catálogo' para ver los productos disponibles."
    elif "producto" in text or "catálogo" in text or "catalogo" in text:
        if not productos:
            reply = "📦 Por ahora no hay productos disponibles. El catálogo se actualiza automáticamente."
        else:
            reply = "🛍️ *Productos disponibles:*\n\n"
            for p in productos:
                precio = f"{p['precio']} {p['moneda']}" if p['precio'] else "Precio no disponible"
                enlace = p['enlace'] or "Sin enlace"
                fuente = p['fuente'] or "Desconocida"
                reply += (
                    f"• *{p['nombre']}*\n"
                    f"  💵 {precio}\n"
                    f"  🌐 {fuente}\n"
                    f"  🔗 {enlace}\n\n"
                )
    else:
        reply = "💬 No entendí. Escribí 'productos' o 'catálogo' para ver lo disponible."

    # --- ENVIAR RESPUESTA A TELEGRAM ---
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"},
        )

    return {"ok": True}

# --- ROOT SIMPLE PARA COMPROBAR ESTADO ---
@app.get("/")
def root():
    return {"status": "Bot de ventas activo 🚀"}
