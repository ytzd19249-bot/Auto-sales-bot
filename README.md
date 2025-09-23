# Bot de Ventas 🤖🛍️

Este bot está diseñado para responder de forma natural a los clientes, mostrando productos desde la base de datos y actuando como un vendedor humano.

## Archivos incluidos
- `main.py`: lógica principal del bot
- `db.py`: conexión a la base de datos PostgreSQL
- `requirements.txt`: dependencias
- `Procfile`: para desplegar en Heroku
- `runtime.txt`: versión de Python
- `render.yaml`: config para Render
- `example.env`: variables de entorno de ejemplo

## Variables de entorno
- `TELEGRAM_TOKEN`: token del bot de Telegram
- `DATABASE_URL`: URL de la base de datos PostgreSQL
- `ADMIN_TOKEN`: clave de admin opcional

## Despliegue en Render
1. Subir el proyecto
2. Configurar variables de entorno en el panel
3. Establecer webhook en Telegram

