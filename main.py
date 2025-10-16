from fastapi import FastAPI, Request, Header, HTTPException
from typing import List, Optional
import os
from datetime import datetime, timedelta

# DB (SQLAlchemy)
from sqlalchemy import create_engine, Integer, String, Float, DateTime, Boolean, Text, func
from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column

# Scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===== App =====
app = FastAPI()

# ===== Env =====
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not ADMIN_TOKEN:
    print("⚠️ Falta ADMIN_TOKEN")
if not DATABASE_URL:
    print("⚠️ Falta DATABASE_URL")

# ===== DB setup =====
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Product(Base):
    __tablename__ = "sales_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ext_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)  # id externo (afiliado)
    title: Mapped[str] = mapped_column(String(500))
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    purchased_count: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

Base.metadata.create_all(engine)

# ===== Auth helper =====
def require_token(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

# ===== Schemas =====
from pydantic import BaseModel

class InProduct(BaseModel):
    title: str
    url: Optional[str] = None
    price: Optional[float] = None
    image: Optional[str] = None
    source: Optional[str] = None
    ext_id: Optional[str] = None

class PurchaseEvent(BaseModel):
    product_id: int
    qty: int = 1

# ===== Routes =====
@app.get("/")
def health():
    return {"ok": True, "service": "bot-ventas", "message": "En línea ✅"}

@app.post("/sales/ingest")
def ingest(products: List[InProduct], authorization: Optional[str] = Header(None)):
    require_token(authorization)
    db = SessionLocal()
    try:
        inserted, updated = 0, 0
        for p in products:
            # upsert por ext_id o por (title+url)
            rec = None
            if p.ext_id:
                rec = db.query(Product).filter(Product.ext_id == p.ext_id).one_or_none()
            if not rec:
                rec = db.query(Product).filter(
                    Product.title == p.title,
                    Product.url == p.url
                ).one_or_none()

            if rec:
                # update
                if p.price is not None:
                    rec.price = p.price
                if p.image:
                    rec.image = p.image
                if p.source:
                    rec.source = p.source
                rec.updated_at = datetime.utcnow()
                updated += 1
            else:
                # insert
                rec = Product(
                    ext_id=p.ext_id,
                    title=p.title,
                    price=p.price,
                    url=p.url,
                    image=p.image,
                    source=p.source,
                )
                db.add(rec)
                inserted += 1

        db.commit()
        return {"ok": True, "inserted": inserted, "updated": updated}
    finally:
        db.close()

@app.post("/sales/purchase")
def register_purchase(evt: PurchaseEvent, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    db = SessionLocal()
    try:
        prod = db.query(Product).filter(Product.id == evt.product_id).one_or_none()
        if not prod:
            raise HTTPException(status_code=404, detail="Product not found")
        prod.purchased_count += max(1, evt.qty)
        prod.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "product_id": prod.id, "purchased_count": prod.purchased_count}
    finally:
        db.close()

# ===== Limpieza automática =====
# Regla:
# - Archivar si lleva >= 60 días sin compras (purchased_count == 0)
# - Borrar si lleva >= 120 días y purchased_count == 0
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("cron", hour=3)  # todos los días 03:00 UTC
def cleanup_job():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        limit_archive = now - timedelta(days=60)
        limit_delete  = now - timedelta(days=120)

        # Archivar (marcar)
        to_archive = db.query(Product).filter(
            Product.purchased_count == 0,
            Product.archived == False,
            Product.created_at <= limit_archive
        ).all()
        for r in to_archive:
            r.archived = True
            r.updated_at = now

        # Borrar definitivos
        deleted = db.query(Product).filter(
            Product.purchased_count == 0,
            Product.created_at <= limit_delete
        ).delete(synchronize_session=False)

        db.commit()
        print(f"🧹 Limpieza ventas: archivados={len(to_archive)}, eliminados={deleted}")
    finally:
        db.close()

@app.on_event("startup")
async def startup():
    print("🚀 bot-ventas en línea.")
    try:
        scheduler.start()
    except Exception:
        # si ya estaba iniciado por hot-reload, ignorar
        pass
