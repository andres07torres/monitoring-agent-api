from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class SystemStats(BaseModel):
    timestamp: str
    cpu_percent: float
    cpu_cores: int
    cpu_frequency: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float

class HealthCheckResponse(BaseModel):
    status: int
    message: str

class Alert(BaseModel):
    id: str
    severity: str
    message: str

class CommandRequest(BaseModel):
    command: str

class CommandResponse(BaseModel):
    output: str
    exitCode: int

class PowerActionResponse(BaseModel):
    success: bool
    message: str
