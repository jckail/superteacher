from pydantic import BaseModel

class VersionInfo(BaseModel):
    version: str
    git_commit: str
