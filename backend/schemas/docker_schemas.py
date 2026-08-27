from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ContainerBase(BaseModel):
    id: str
    name: str
    status: str
    image: str

class ContainerInfo(ContainerBase):
    created: Optional[str] = None

class ContainerActionResponse(BaseModel):
    status: str
    id: str

class PruneDetails(BaseModel):
    containers: Any
    images: Any
    networks: Any
    volumes: Any

class PruneResponse(BaseModel):
    status: str
    details: PruneDetails

class LogsResponse(BaseModel):
    logs: List[str]
