from fastapi import FastAPI
import os
import requests

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")

@app.get("/")
def home():
    return {"message": "Hola, Render está funcionando 🚀"}

# Ruta para configurar el webhook
@app.get("/set_webhook")
def set_webhook():
    if not TELEGRAM_TOKEN or not PUBLIC_URL:
        return {"error": "Faltan TELEGRAM_TOKEN o PUBLIC_URL"}
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    payload = {"url": f"{PUBLIC_URL}/webhook/{TELEGRAM_TOKEN}"}
    r = requests.post(url, data=payload)
    return r.json()
