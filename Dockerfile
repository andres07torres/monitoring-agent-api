FROM python:3.10-slim

# Evitar que Python escriba archivos .pyc y forzar el log en consola
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero (aprovecha la caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del proyecto
COPY . .

# Agregar la carpeta backend al PYTHONPATH para que encuentre los módulos (api, schemas, etc)
ENV PYTHONPATH=/app/backend

# Exponer el puerto 8001 (que es el que espera Cloudflare)
EXPOSE 8001

# Levantar el servidor con Uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
