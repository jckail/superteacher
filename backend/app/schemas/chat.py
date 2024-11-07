from pydantic import BaseModel
from typing import List, Optional

class Message(BaseModel):
    role: str
    content: str

class ChatMessage(BaseModel):
    message: str
    context: Optional[str]

class ChatResponse(BaseModel):
    response: str
    context: Optional[str]
