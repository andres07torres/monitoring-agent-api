# 🐳 InfraMonitor - Agente Orquestador API

![Estado](https://img.shields.io/badge/Desarrollo-Completado-success?style=for-the-badge&logo=checkmarx)
![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Container-2496ED?style=for-the-badge&logo=docker&logoColor=white)

Backend robusto (Agente Orquestador) diseñado para monitorear servidores Ubuntu y administrar contenedores Docker de forma remota y segura. Funciona como el "cerebro" detrás de la aplicación móvil **InfraMonitor (Android)**, traduciendo las peticiones del teléfono en comandos de sistema y métricas en tiempo real.

## 🚀 Características Principales

- **Monitoreo en Tiempo Real**: Telemetría exacta del host leyendo el uso de CPU (núcleos y GHz), RAM y almacenamiento vía `psutil`.
- **Orquestación de Docker**: Control total de contenedores locales.
  - Iniciar, detener, pausar, reiniciar y eliminar contenedores.
  - Limpieza del sistema (Prune) y lectura de Logs en vivo.
- **Terminal Remota (Diagnóstico)**: Ejecución de comandos del sistema (`ping`, `ls`, etc.) enviados desde el móvil directamente a la terminal de Ubuntu.
- **Comprobación de Salud (Healthchecks)**: Verificación asíncrona de disponibilidad de URLs y servicios de terceros.
- **Seguridad (Zero Trust)**: Bloqueo de peticiones no autorizadas mediante interceptores y validación de `X-API-Key` en cada solicitud.

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
└── requirements.txt     # Listado de librerías y dependencias
```

## ⚙️ Configuración del Entorno (.env)

El proyecto utiliza variables de entorno para máxima seguridad. Para configurar la comunicación segura entre el servidor y el cliente:

1. Renombra el archivo `.env.example` a `.env` (o crea uno nuevo).
2. **Durante la instalación, se generará una clave en el archivo `.env` (`API_SECRET_KEY`). Copia esa clave y pégala en la aplicación móvil para autorizar el acceso.**
3. Ejecuta el servidor (Uvicorn buscará este archivo automáticamente).

---
Desarrollado con ❤️ para llevar el control de la infraestructura a tu bolsillo.
