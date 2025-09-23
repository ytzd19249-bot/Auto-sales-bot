from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Tomamos la variable de entorno DATABASE_URL desde Render
DATABASE_URL = os.getenv("DATABASE_URL")

# Creamos el motor con verificación de conexión (pool_pre_ping)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

# Sesión para interactuar con la BD
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base de datos declarativa
Base = declarative_base()

# Dependencia para usar en los endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
