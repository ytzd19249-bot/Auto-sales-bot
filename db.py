from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# URL de la base de datos (Render → Variables de entorno)
DATABASE_URL = os.getenv("DATABASE_URL")

# Crear el motor con SSL obligatorio
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Modelo Producto
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    precio = Column(Float, nullable=False)
    moneda = Column(String, default="USD")
    link = Column(String, nullable=False)
    activo = Column(Boolean, default=True)
