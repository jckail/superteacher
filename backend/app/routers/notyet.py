from fastapi import APIRouter
from ..schemas.notyet import NotYetResponse

router = APIRouter(
    prefix="/api/notyet",
    tags=["notyet"]
)

@router.get("", response_model=NotYetResponse)
async def not_yet_implemented():
    return {"message": "route not yet implemented"}
