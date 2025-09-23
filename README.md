# Bot de Ventas 🤖🛒

Este es un bot de ventas con integración a Telegram y base de datos en PostgreSQL.

## Configuración

1. Clona el repositorio o descarga el ZIP.
2. Crea un archivo `.env` basado en `example.env`.
3. Instala dependencias con:
   ```bash
   pip install -r requirements.txt
   ```
4. Ejecuta con:
   ```bash
   uvicorn main:app --reload
   ```

## Despliegue en Render

- Configura las variables de entorno en Render (`TELEGRAM_TOKEN`, `DATABASE_URL`).
- Render usará `render.yaml` y `Procfile` para desplegar automáticamente.

## Autor
Cypherbolt 🤘
