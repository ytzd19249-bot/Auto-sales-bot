# db.py
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# URL de la base de datos (Render le da esta variable en el dashboard)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # fallback por si Render no la pasa
    DATABASE_URL = "postgresql+psycopg2://usuario:clave@host:5432/base?sslmode=require"

# Conexión
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base de modelos
Base = declarative_base()

# Modelo ejemplo de productos (puede agregar más tablas)
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    precio = Column(Float, nullable=False)


# Crear las tablas si no existen
def init_db():
    Base.metadata.create_all(bind=engine)
