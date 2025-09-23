from fastapi import FastAPI
from db import init_db, SessionLocal, Producto

app = FastAPI()

# Inicializar DB al arrancar
@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def home():
    return {"status": "ok", "message": "Bot de ventas activo y conectado a la DB"}


# Ejemplo de endpoint para listar productos
@app.get("/productos")
def listar_productos():
    db = SessionLocal()
    productos = db.query(Producto).filter(Producto.activo == True).all()
    db.close()
    return productos
