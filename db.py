# db.py
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Cargar la URL de la base de datos desde las variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Crear motor de conexión
engine = create_engine(DATABASE_URL)

# Crear base declarativa
Base = declarative_base()

# Definir tabla de productos
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    precio = Column(Float, nullable=False)
    moneda = Column(String, default="USD")
    link = Column(String, nullable=True)

# Crear sesión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Inicializar DB
def init_db():
    Base.metadata.create_all(bind=engine)
