import os
from fastapi import FastAPI, Request, Header, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, text
from datetime import datetime
import asyncio

# ───────────────────────────────
# CONFIGURACIÓN
# ───────────────────────────────
app = FastAPI(title="Bot de Ventas", version="1.0")

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "ventas_admin_12345")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

scheduler = AsyncIOScheduler(timezone="America/Costa_Rica")

# ───────────────────────────────
# ENDPOINT PARA RECIBIR PRODUCTOS
# ───────────────────────────────
@app.post("/ingestion/productos")
async def recibir_productos(req: Request, authorization: str = Header(None)):
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="No autorizado")

    data = await req.json()
    productos = data.get("productos", [])

    if not productos:
        return {"ok": False, "mensaje": "Sin productos recibidos"}

    insertados = 0
    for p in productos:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO productos (titulo, precio, categoria, link_afiliado, fecha)
                        VALUES (:titulo, :precio, :categoria, :link_afiliado, NOW())
                        ON CONFLICT (titulo) DO UPDATE
                        SET precio = EXCLUDED.precio,
                            categoria = EXCLUDED.categoria,
                            link_afiliado = EXCLUDED.link_afiliado,
                            fecha = NOW();
                    """),
                    {
                        "titulo": p.get("titulo"),
                        "precio": p.get("precio"),
                        "categoria": p.get("categoria"),
                        "link_afiliado": p.get("link_afiliado"),
                    },
                )
                insertados += 1
        except Exception as e:
            print(f"[VENTAS] ❌ Error guardando producto: {e}")

    print(f"[VENTAS] ✅ Productos insertados/actualizados: {insertados}")
    return {"ok": True, "insertados": insertados}

# ───────────────────────────────
# LIMPIEZA AUTOMÁTICA DE PRODUCTOS VIEJOS
# ───────────────────────────────
def limpiar_productos_viejos():
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM productos
                    WHERE fecha < NOW() - INTERVAL '120 days';
                """)
            )
        print(f"[VENTAS] 🧹 Limpieza completada ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    except Exception as e:
        print(f"[VENTAS] ⚠️ Error limpiando productos: {e}")

# ───────────────────────────────
# TAREAS PROGRAMADAS
# ───────────────────────────────
@scheduler.scheduled_job("interval", hours=12)
def ciclo_limpieza():
    limpiar_productos_viejos()

@app.on_event("startup")
async def start_scheduler():
    scheduler.start()
    print("[VENTAS] 🚀 Bot de ventas iniciado y scheduler corriendo cada 12h.")

# ───────────────────────────────
# ENDPOINT PRINCIPAL
# ───────────────────────────────
@app.get("/")
def root():
    return {"ok": True, "bot": "ventas", "status": "activo"}
