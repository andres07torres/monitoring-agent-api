#!/bin/bash
# Script para iniciar la API de InfraMonitor con Bash

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH="$APP_DIR/backend"

# Iniciar Uvicorn
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
