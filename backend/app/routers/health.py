from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..schemas.health import HealthStatus
from ..models.database import get_db

router = APIRouter(
    prefix="/api/health",
    tags=["health"]
)

@router.get("", response_model=HealthStatus)
async def health_check(db: Session = Depends(get_db)):
    try:
        # Test database connection
        db.execute("SELECT 1")
        db_status = "healthy"
        db_message = "Database connection successful"
    except Exception as e:
        db_status = "unhealthy"
        db_message = f"Database error: {str(e)}"

    # Overall status is healthy only if all checks pass
    overall_status = "healthy" if db_status == "healthy" else "unhealthy"
    
    return {
        "status": overall_status,
        "details": {
            "database": db_message,
            "server": "Server is running"
        }
    }
