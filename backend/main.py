from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import version, db, health, notyet
from app.models.database import init_db

# Initialize database
init_db()

app = FastAPI(title="EduTrack Pro API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(version.router)
app.include_router(db.router)
app.include_router(health.router)
app.include_router(notyet.router)
