# db.py
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base

# Leer la URL desde variables de entorno (Render -> Environment)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # fallback (solo local/testing) — reemplazar si hace falta
    DATABASE_URL = "postgresql+psycopg2://usuario:clave@host:5432/dbname?sslmode=require"

# Crear engine con protección de conexión (reintentos / pre-ping)
# connect_args incluye sslmode por seguridad adicional
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"sslmode": "require"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Modelo Producto (tabla compartida con Bot Investigador)
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), nullable=False, index=True)
    descripcion = Column(Text, nullable=True)
    precio = Column(Float, nullable=False, default=0.0)
    moneda = Column(String(10), nullable=False, default="USD")
    link = Column(String(1024), nullable=True)
    source = Column(String(100), nullable=True)   # ej: Hotmart, Amazon, etc.
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Crear tablas si no existen (llamar en startup)."""
    Base.metadata.create_all(bind=engine)
