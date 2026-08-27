# Monitoring Agent API

Este es el backend oficial (agente orquestador) diseñado para monitorear y administrar servidores Ubuntu y contenedores Docker desde la aplicación móvil InfraMonitor (Android).

## Características
- **Monitoreo en Tiempo Real:** Uso de CPU, RAM, discos y más (a través de `psutil`).
- **Administración de Docker:** Iniciar, detener, pausar, reiniciar, borrar y limpiar contenedores e imágenes.
- **Terminal Remota:** Ejecución de comandos de diagnóstico (`ping`, `ls`, etc.) directo desde la app móvil.
- **Healthchecks:** Verificación de estado HTTP de los diferentes servicios de infraestructura.

## Instalación y Despliegue

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/andres07torres/monitoring-agent-api.git
   cd monitoring-agent-api
   ```

2. **Crear entorno virtual e instalar dependencias:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configuración de Seguridad (IMPORTANTE):**
   Copia el archivo de entorno de ejemplo para crear el tuyo:
   ```bash
   cp .env.example .env
   ```
   > 🔑 **Durante la instalación, se generará una clave en el archivo `.env` (`API_SECRET_KEY`). Copia esa clave y pégala en la aplicación móvil para autorizar el acceso.**

4. **Ejecutar el Servidor:**
   ```bash
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8001
   ```

## Documentación de la API
Una vez que el servidor esté corriendo, puedes acceder a la documentación interactiva de los endpoints (Swagger UI) navegando a:
`http://[TU_IP]:8001/docs`

## Tecnologías Utilizadas
- **FastAPI** (Web Framework asíncrono)
- **Pydantic** (Validación de esquemas y DTOs)
- **Docker SDK for Python**
- **Psutil** (Métricas de hardware)
