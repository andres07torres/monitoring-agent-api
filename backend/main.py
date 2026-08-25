from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
import os

# Cargar variables de entorno desde el archivo .env
load_dotenv()

from api.routes import router as http_router
from api.ws_routes import ws_router

app = FastAPI(title="Server Orchestration Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_router)
app.include_router(ws_router)

@app.get("/")
def read_root():
    return {"status": "Agent is running", "agent": "FastAPI Orquestador"}

if __name__ == "__main__":
    # Se expone en el 8000 para que Traefik/Cloudflare Tunnel lo consuman
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
