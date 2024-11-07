from pydantic import BaseModel

class NotYetResponse(BaseModel):
    message: str
