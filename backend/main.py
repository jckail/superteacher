from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routers import health, version, db, chat
from backend.app.models.database import init_db

app = FastAPI()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers without duplicate prefixes
app.include_router(health.router)  # Will be available at /health
app.include_router(version.router)  # Will be available at /version
app.include_router(db.router)      # Will be available at /db
app.include_router(chat.router)    # Will be available at /chat
