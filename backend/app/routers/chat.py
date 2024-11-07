from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict
from anthropic import Anthropic, APIError, APIConnectionError
import os
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Initialize router
router = APIRouter()

# Connection Manager for WebSocket clients
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.page_contexts: Dict[str, str] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.page_contexts:
            del self.page_contexts[client_id]

    def store_context(self, client_id: str, context: str):
        self.page_contexts[client_id] = context

    def get_context(self, client_id: str) -> str:
        return self.page_contexts.get(client_id, '')

    async def send_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json({
                "message": message,
                "sender": "assistant"
            })

manager = ConnectionManager()

# Initialize Anthropic client
def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise Exception("ANTHROPIC_API_KEY not found in environment variables")
    return Anthropic(api_key=api_key)

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    client = get_anthropic_client()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            parsed_data = json.loads(data)
            
            try:
                if parsed_data["type"] == "context":
                    # Store the page context for this client
                    manager.store_context(client_id, parsed_data["content"])
                    continue
                
                # Get the stored context for this client
                context = manager.get_context(client_id)
                
                # Create a message to Claude with context about being an educational assistant
                system_prompt = """You are an educational assistant helping teachers analyze student performance and provide insights. 
                Keep responses focused on academic context and student success. Be concise but informative.
                You have access to the current page content and structure to provide more contextual responses."""
                
                # Construct the user message with context
                user_message = f"""Page Context: {context}

User Message: {parsed_data["content"]}

Please provide a response that takes into account both the user's message and the current page context."""
                
                # Send message to Claude
                response = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=1024,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": user_message
                    }]
                )
                
                # Extract the response text and send back to client
                response_text = response.content[0].text
                await manager.send_message(response_text, client_id)
                
            except APIError as e:
                await manager.send_message(f"API Error: {str(e)}", client_id)
            except APIConnectionError as e:
                await manager.send_message(f"Connection Error: {str(e)}", client_id)
            except Exception as e:
                await manager.send_message(f"Error: {str(e)}", client_id)
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
