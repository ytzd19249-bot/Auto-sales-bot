# db.py
import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base

# Leer URL de la base desde variables de entorno (Render)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # ⚠️ Solo fallback para pruebas locales
    DATABASE_URL = "postgresql+psycopg2://usuario:clave@host:5432/dbname"

# Crear engine con sslmode=require (Render usa SSL)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"sslmode": "require"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelo compartido con el bot investigador
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), nullable=False, index=True)
    descripcion = Column(Text, nullable=True)
    precio = Column(Float, nullable=False, default=0.0)
    moneda = Column(String(10), nullable=False, default="USD")
    link = Column(String(1024), nullable=True)
    source = Column(String(100), nullable=True)  # Ej: Hotmart, Amazon
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Crear tablas si no existen (se ejecuta en el arranque)."""
    Base.metadata.create_all(bind=engine)
