#!/bin/bash

# Salir si ocurre un error
set -e

echo "================================================="
echo "🚀 Instalador Automático - InfraMonitor API"
echo "================================================="

# Obtener el directorio actual y el usuario
APP_DIR=$(pwd)
CURRENT_USER=$(whoami)

echo "[1/5] Verificando dependencias del sistema (requiere permisos sudo)..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip

echo "[2/5] Creando entorno virtual e instalando dependencias..."
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

echo "[3/5] Configurando clave secreta (.env)..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        echo 'API_SECRET_KEY=""' > .env
    fi
fi

# Validar o generar clave secreta aleatoria en .env si está vacía
SECRET_KEY=$(python3 -c "
import sys, os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from main import ensure_api_secret_key
print(ensure_api_secret_key('.env'))
")
chmod 600 .env
echo "¡Archivo .env configurado de forma segura!"

# Validar permisos de Docker
if ! groups $CURRENT_USER | grep -q '\bdocker\b'; then
    echo "⚠️ ADVERTENCIA: El usuario $CURRENT_USER no pertenece al grupo 'docker'."
    echo "Es posible que la API no tenga permisos para administrar contenedores."
    echo "Considera ejecutar: sudo usermod -aG docker $CURRENT_USER"
fi

echo "[4/5] Creando servicio de fondo (Systemd) y permisos de energía..."

# Permisos sudoers para apagar/reiniciar sin contraseña
SUDOERS_FILE="/etc/sudoers.d/monitoring-agent-power"
echo "$CURRENT_USER ALL=(ALL) NOPASSWD: /sbin/shutdown, /sbin/reboot, /bin/systemctl" | sudo tee $SUDOERS_FILE > /dev/null
sudo chmod 0440 $SUDOERS_FILE

sudo tee /etc/systemd/system/monitoring-agent.service > /dev/null <<EOF
[Unit]
Description=Monitoring Agent API (FastAPI)
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR/backend
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

# Recargar y activar el servicio
sudo systemctl daemon-reload
sudo systemctl enable monitoring-agent
sudo systemctl restart monitoring-agent

echo "[5/5] ¡Instalación Completada!"
echo "================================================="
echo "✅ El orquestador está corriendo en segundo plano."
echo "✅ Se iniciará automáticamente si el servidor se reinicia."
echo ""
echo "📱🔑 TU CLAVE SECRETA PARA LA APP MÓVIL ES:"
echo "-------------------------------------------------"
echo "$SECRET_KEY"
echo "-------------------------------------------------"
