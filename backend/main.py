import os
import re
import secrets
import string
import shutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn

def ensure_api_secret_key(dotenv_path: str) -> str:
    """
    Verifica si existe el archivo .env y si API_SECRET_KEY está vacía (ej. API_SECRET_KEY="").
    Si está vacía, genera automáticamente una contraseña segura y la escribe dentro de las comillas en .env.
    """
    if not os.path.exists(dotenv_path):
        example_path = os.path.join(os.path.dirname(dotenv_path), ".env.example")
        if os.path.exists(example_path):
            shutil.copyfile(example_path, dotenv_path)
        else:
            with open(dotenv_path, "w", encoding="utf-8") as f:
                f.write('API_SECRET_KEY=""\n')

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[!] No se pudo leer {dotenv_path}: {e}")
        return os.getenv("API_SECRET_KEY", "")

    pattern = r"^[ \t]*API_SECRET_KEY[ \t]*=[ \t]*(['\"]?)(.*?)\1[ \t]*(?:#.*)?$"
    match = re.search(pattern, content, flags=re.MULTILINE)

    def generate_random_password(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    secret_key = None
    needs_update = False

    if match:
        val = match.group(2).strip()
        if not val or val == "cambiar_por_una_llave_segura_generada_aleatoriamente":
            secret_key = generate_random_password(16)
            content = re.sub(
                r"^[ \t]*API_SECRET_KEY[ \t]*=[ \t]*(['\"]?)(?:.*?)\1([ \t]*(?:#.*)?)$",
                lambda m: f'API_SECRET_KEY="{secret_key}"{m.group(2)}',
                content,
                flags=re.MULTILINE
            )
            needs_update = True
        else:
            secret_key = val
    else:
        secret_key = generate_random_password(16)
        if content and not content.endswith("\n"):
            content += "\n"
        content += f'API_SECRET_KEY="{secret_key}"\n'
        needs_update = True

    if needs_update:
        try:
            with open(dotenv_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("=" * 65)
            print("[SEGURIDAD] API_SECRET_KEY estaba vacía en .env.")
            print("Se generó automáticamente una nueva contraseña aleatoria:")
            print(f"-> {secret_key}")
            print(f"Guardada dentro de las comillas en: {dotenv_path}")
            print("=" * 65)
        except Exception as e:
            print(f"[!] No se pudo escribir en {dotenv_path}: {e}")

    if secret_key:
        os.environ["API_SECRET_KEY"] = secret_key

    return secret_key

# Cargar variables de entorno desde el archivo .env en la raíz del proyecto
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
ensure_api_secret_key(dotenv_path)
load_dotenv(dotenv_path=dotenv_path, override=True)

from api.routes import router as http_router
from api.ws_routes import ws_router, api_ws_router

app = FastAPI(
    title="InfraMonitor Backend Agent API",
    description="Servidor de telemetría y orquestación para la aplicación móvil InfraMonitor.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_router)
app.include_router(ws_router)
app.include_router(api_ws_router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "agent": "InfraMonitor Backend Agent",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", 8001))
    host = os.getenv("API_HOST", "0.0.0.0")
    app_target = "backend.main:app" if os.path.exists("backend") else "main:app"
    uvicorn.run(app_target, host=host, port=port, reload=True)
