# db.py
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base

# Base de datos SQLite
DATABASE_URL = "sqlite:///./productos.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Modelo de productos
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    precio = Column(Float, nullable=True)
    moneda = Column(String(10), default="USD")
    link = Column(String(500), nullable=True)
    source = Column(String(100), nullable=True)
    activo = Column(Boolean, default=True)


def init_db():
    Base.metadata.create_all(bind=engine)
