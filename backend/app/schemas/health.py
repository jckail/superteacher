from pydantic import BaseModel
from typing import Dict

class HealthStatus(BaseModel):
    status: str
    details: Dict[str, str]
