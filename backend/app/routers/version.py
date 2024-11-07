from fastapi import APIRouter, HTTPException
from git import Repo, InvalidGitRepositoryError
import os
from dotenv import load_dotenv
from ..schemas.version import VersionInfo

# Load environment variables
load_dotenv()

router = APIRouter(
    prefix="/version",
    tags=["version"]
)

@router.get("", response_model=VersionInfo)
async def get_version():
    try:
        # Get version from environment variable
        version = os.getenv("VERSION", "unknown")
        
        try:
            # Try to get git commit hash
            repo = Repo(search_parent_directories=True)
            git_commit = repo.head.object.hexsha
        except (InvalidGitRepositoryError, Exception):
            # If git info is not available, use a placeholder
            git_commit = "development"
        
        return {"version": version, "git_commit": git_commit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
