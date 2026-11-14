from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ContainerBase(BaseModel):
    id: str
    name: str
    status: str
    cpu_usage: float = 0.0
    ram_usage: float = 0.0
    image: Optional[str] = None

class ContainerInfo(ContainerBase):
    created: Optional[str] = None

class ContainerActionResponse(BaseModel):
    status: str
    id: str
    message: Optional[str] = None

class PruneDetails(BaseModel):
    containers: Optional[Any] = None
    images: Optional[Any] = None
    networks: Optional[Any] = None
    volumes: Optional[Any] = None

class PruneResponse(BaseModel):
    status: str
    message: Optional[str] = None
    details: Optional[Any] = None

class LogsResponse(BaseModel):
    logs: List[str]
