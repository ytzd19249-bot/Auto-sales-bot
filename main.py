import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, validator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text
import httpx

# ============================
#        CONFIG GLOBAL
# ============================
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")                       # https://bot-ventas.onrender.com
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")               # para IA conversacional
DATABASE_URL = os.getenv("DATABASE_URL")
HOURS_BETWEEN_CYCLES = int(os.getenv("HOURS_BETWEEN_CYCLES", "12"))
DAYS_TO_DELETE = 120                                       # borrar solo si >120 días y ventas = 0

WEBHOOK_URL = f"{PUBLIC_URL}/webhook"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
client = httpx.AsyncClient(timeout=30)
scheduler = AsyncIOScheduler()


# ============================
#        SCHEMAS API
# ============================
class ProductoIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=300)
    precio: float = Field(..., ge=0)
    link: Optional[HttpUrl] = None                  # link original de la oferta
    link_afiliado: HttpUrl                          # link con tu ID de afiliado (OBLIGATORIO)
    network: str = Field(..., min_length=2)         # p.ej. "hotmart", "clickbank", "amazon"
    commission_pct: Optional[float] = Field(None, ge=0, le=100)
    commission_value: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field("USD", min_length=3, max_length=3)

    @validator("network")
    def network_lower(cls, v):
        return v.strip().lower()

class LoteProductos(BaseModel):
    productos: List[ProductoIn]


# ============================
#    DB: tablas y helpers
# ============================
def ensure_tables():
    """
    Tabla 'productos' es la ÚNICA del bot de ventas.
    Guarda productos YA afiliados por el bot investigador.
    """
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS productos (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio NUMERIC(10,2) NOT NULL,
            link TEXT,
            link_afiliado TEXT UNIQUE NOT NULL,
            network TEXT NOT NULL,
            commission_pct NUMERIC(6,2),
            commission_value NUMERIC(10,2),
            currency CHAR(3) DEFAULT 'USD',
            fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            ventas INT NOT NULL DEFAULT 0
        );
        """))
        # Índices útiles
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_productos_fecha ON productos(fecha);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_productos_network ON productos(network);"))

def upsert_productos(items: List[ProductoIn]):
    """
    Inserta/actualiza por link_afiliado (UNIQUE).
    Si ya existe, actualiza nombre/precio/commission y refresca fecha.
    """
    with engine.begin() as conn:
        for p in items:
            conn.execute(text("""
                INSERT INTO productos (nombre, precio, link, link_afiliado, network,
                                       commission_pct, commission_value, currency, fecha)
                VALUES (:nombre, :precio, :link, :link_afiliado, :network,
                        :commission_pct, :commission_value, :currency, NOW())
                ON CONFLICT (link_afiliado) DO UPDATE
                SET nombre = EXCLUDED.nombre,
                    precio = EXCLUDED.precio,
                    link = COALESCE(EXCLUDED.link, productos.link),
                    network = EXCLUDED.network,
                    commission_pct = EXCLUDED.commission_pct,
                    commission_value = EXCLUDED.commission_value,
                    currency = EXCLUDED.currency,
                    fecha = NOW();
            """), dict(
                nombre=p.nombre,
                precio=p.precio,
                link=str(p.link) if p.link else None,
                link_afiliado=str(p.link_afiliado),
                network=p.network,
                commission_pct=p.commission_pct,
                commission_value=p.commission_value,
                currency=p.currency
            ))

def cleanup_old_products():
    """Borra SOLO productos con más de 120 días y SIN ventas."""
    limite = datetime.utcnow() - timedelta(days=DAYS_TO_DELETE)
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM productos
            WHERE fecha < :limite AND ventas = 0
        """), {"limite": limite})

def contador_productos():
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM productos;")).scalar() or 0
        sin_ventas = conn.execute(text("SELECT COUNT(*) FROM productos WHERE ventas = 0;")).scalar() or 0
        viejos = conn.execute(text("""
            SELECT COUNT(*) FROM productos
            WHERE fecha < :limite AND ventas = 0
        """), {"limite": datetime.utcnow() - timedelta(days=DAYS_TO_DELETE)}).scalar() or 0
    return total, sin_ventas, viejos


# ============================
#   LÓGICA AUTOMÁTICA (12h)
# ============================
async def ciclo_mantenimiento():
    """
    Cada N horas:
    - Limpia productos sin ventas > 120 días.
    (El investigador ya envía afiliados; aquí no se investiga nada).
    """
    print("🧹 Ciclo mantenimiento: limpiando catálogo viejo sin ventas…")
    cleanup_old_products()
    print("✅ Limpieza completada.")


# ============================
#   TELEGRAM: helpers
# ============================
async def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    await client.post(url, json={"chat_id": chat_id, "text": text})

async def tg_set_webhook():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    return await client.post(url, json={"url": WEBHOOK_URL})


# ============================
#   IA CONVERSACIONAL
# ============================
async def responder_con_ia(texto_usuario: str) -> str:
    if not OPENAI_API_KEY:
        return "La IA no está configurada (falta OPENAI_API_KEY)."

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-5.1-mini",
        "input": [
            {"role": "system", "content":
             "Eres un asistente de VENTAS con tono tico, directo y amable. "
             "Responde corto, útil y con foco en vender/ayudar. "
             "Si preguntan por estado, explica el flujo: investigador manda productos YA afiliados; "
             "ventas guarda y mantiene la base (limpieza 120 días sin ventas)."
            },
            {"role": "user", "content": texto_usuario}
        ]
    }
    try:
        resp = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
        data = resp.json()
        return data.get("output_text") or "Listo."
    except Exception as e:
        print("Error IA:", e)
        return "Hubo un problema generando la respuesta de IA."


# ============================
#         RUTAS HTTP
# ============================
@app.get("/")
async def home():
    return {"message": "Bot de ventas activo. Recibiendo productos YA afiliados del investigador."}

@app.get("/status")
async def status():
    total, sin_ventas, viejos = contador_productos()
    return {
        "ok": True,
        "total_productos": total,
        "sin_ventas": sin_ventas,
        f"sin_ventas_mas_{DAYS_TO_DELETE}_dias": viejos
    }

@app.post("/recibir_productos")
async def recibir_productos(payload: LoteProductos):
    """
    Endpoint para el BOT INVESTIGADOR.
    Recibe productos YA afiliados y los inserta/actualiza en la tabla 'productos'.
    """
    items = payload.productos
    if not items:
        raise HTTPException(status_code=400, detail="No se recibieron productos.")

    # Validación adicional: todos deben traer link_afiliado
    faltantes = [p.nombre for p in items if not p.link_afiliado]
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan link_afiliado en: {', '.join(faltantes)}"
        )

    upsert_productos(items)
    return {"ok": True, "insertados_actualizados": len(items)}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("📨 Webhook:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        texto = (data["message"].get("text") or "").strip()

        # Atajos (opcionales)
        if texto == "/status":
            total, sin_ventas, viejos = contador_productos()
            await tg_send(
                chat_id,
                f"✅ Activo.\nProductos: {total}\nSin ventas: {sin_ventas}\n"
                f"Sin ventas > {DAYS_TO_DELETE} días: {viejos}"
            )
            return JSONResponse({"ok": True})
        if texto == "/start":
            await tg_send(chat_id, "👋 ¡Pura vida! Decime qué ocupás y te ayudo a vender.")
            return JSONResponse({"ok": True})
        if texto == ADMIN_TOKEN:
            await tg_send(chat_id, "🔐 Admin OK.")
            return JSONResponse({"ok": True})

        # Conversación libre con IA
        respuesta = await responder_con_ia(texto)
        await tg_send(chat_id, respuesta)

    return JSONResponse({"ok": True})


# ============================
#    CICLO DE VIDA SERVIDOR
# ============================
@app.on_event("startup")
async def on_startup():
    print("🚀 Iniciando bot de ventas…")
    ensure_tables()
    try:
        r = await tg_set_webhook()
        print("Webhook:", r.text)
    except Exception as e:
        print("Error configurando webhook:", e)

    # Mantenimiento automático cada N horas (por defecto 12)
    scheduler.add_job(
        ciclo_mantenimiento,
        "interval",
        hours=HOURS_BETWEEN_CYCLES,
        next_run_time=datetime.utcnow()
    )
    scheduler.start()
    print("⏰ Scheduler listo.")

@app.on_event("shutdown")
async def on_shutdown():
    await client.aclose()
    print("👋 Bot detenido.")
