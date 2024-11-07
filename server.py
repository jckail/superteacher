import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routers import health, version, db, chat
from backend.app.models.database import init_db
import uvicorn

app = FastAPI()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include WebSocket router first (before static files)
app.include_router(chat.router)

# Include other API routers
app.include_router(health.router, prefix="/api")
app.include_router(version.router, prefix="/api")
app.include_router(db.router, prefix="/api")

# Then mount the frontend build directory
app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["backend", "frontend/build"]
    )
