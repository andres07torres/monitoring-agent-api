# 🐳 InfraMonitor - Agente Orquestador API

![Estado](https://img.shields.io/badge/Desarrollo-Completado-success?style=for-the-badge&logo=checkmarx)
![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Container-2496ED?style=for-the-badge&logo=docker&logoColor=white)

Backend robusto (Agente Orquestador) diseñado para monitorear servidores Ubuntu y administrar contenedores Docker de forma remota y segura. Funciona como el "cerebro" detrás de la aplicación móvil **InfraMonitor (Android)**, traduciendo las peticiones del teléfono en comandos de sistema y métricas en tiempo real.

## 🚀 Características Principales

- **Monitoreo en Tiempo Real**: Telemetría exacta del host leyendo el uso de CPU (núcleos y GHz), RAM y almacenamiento vía `psutil`.
- **Gestión de Energía del Host**: Reinicio (`/api/v1/system/reboot`) y apagado seguro (`/api/v1/system/shutdown`) diferidos para permitir el cierre limpio de sockets y servicios.
- **Orquestación de Docker**: Control total de contenedores locales.
  - Iniciar, detener, pausar, reiniciar y eliminar contenedores.
  - Limpieza del sistema (Prune) y lectura de Logs en vivo.
- **Terminal Remota (Diagnóstico)**: Ejecución de comandos del sistema (`ping`, `ls`, etc.) enviados desde el móvil directamente a la terminal de Ubuntu.
- **Comprobación de Salud (Healthchecks)**: Verificación asíncrona de disponibilidad de URLs y servicios de terceros.
- **Seguridad (Zero Trust y Auto-Key)**: Bloqueo de peticiones no autorizadas mediante interceptores y validación de `X-API-Key`. Si el campo `API_SECRET_KEY=""` se encuentra vacío en `.env`, al iniciar la API con Docker o Bash se genera y escribe automáticamente una contraseña aleatoria dentro de las comillas.

## 🛠️ Stack Tecnológico

- **Lenguaje:** ![Python](https://img.shields.io/badge/-Python-3776AB?style=flat-square&logo=python&logoColor=white) 3.x
- **Web Framework:** ![FastAPI](https://img.shields.io/badge/-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
- **Validación de Datos:** ![Pydantic](https://img.shields.io/badge/-Pydantic-E92063?style=flat-square&logo=pydantic&logoColor=white)
- **Servidor ASGI:** ![Uvicorn](https://img.shields.io/badge/-Uvicorn-499848?style=flat-square&logo=uvicorn&logoColor=white)
- **Integraciones:** Docker SDK for Python, Psutil, Httpx.

## 📂 Estructura del Proyecto

```text
monitoring-agent-api/
├── backend/
│   ├── api/             # Controladores y rutas HTTP/WebSocket
│   ├── schemas/         # DTOs y validación estricta con Pydantic
│   ├── services/        # Lógica de negocio (Interacción con OS y Docker)
│   └── main.py          # Punto de entrada de la aplicación
├── .env.example         # Plantilla de credenciales seguras
├── .gitignore           # Archivos ignorados por el repositorio
├── docker-compose.yml   # Despliegue con Docker y sincronización de .env
├── Dockerfile           # Imagen Docker para el agente
├── install.sh           # Script de despliegue en Ubuntu con Systemd y sudoers
├── run.sh               # Script para ejecutar en terminal con Bash
└── requirements.txt     # Listado de librerías y dependencias
```

## ⚙️ Configuración del Entorno (.env)

El proyecto utiliza variables de entorno para máxima seguridad. Para configurar la comunicación segura entre el servidor y el cliente:

1. Crea o renombra el archivo `.env.example` a `.env`.
2. Si dejas el campo `API_SECRET_KEY=""` vacío, el sistema generará una contraseña criptográficamente segura y la guardará automáticamente dentro de las comillas en el archivo `.env` al arrancar el agente (ya sea con `docker compose up`, `bash run.sh` o `bash install.sh`).
3. Copia esa clave generada e ingrésala en la aplicación móvil para autorizar el acceso.

---
Desarrollado con ❤️ para llevar el control de la infraestructura a tu bolsillo.
