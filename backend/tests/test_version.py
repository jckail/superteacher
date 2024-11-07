import pytest
from unittest.mock import patch, MagicMock
from git.exc import InvalidGitRepositoryError

def test_get_version_success(client):
    """Test successful version retrieval"""
    with patch("app.routers.version.os.getenv") as mock_getenv, \
         patch("app.routers.version.Repo") as mock_repo:
        # Mock environment variable
        mock_getenv.return_value = "1.0.0"
        
        # Mock git repo and commit hash
        mock_head = MagicMock()
        mock_head.object.hexsha = "abcdef1234567890"
        mock_repo.return_value.head = mock_head
        
        response = client.get("/api/version")
        
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0.0"
        assert data["git_commit"] == "abcdef1"

def test_get_version_no_env_var(client):
    """Test version endpoint when VERSION env var is not set"""
    with patch("app.routers.version.os.getenv") as mock_getenv, \
         patch("app.routers.version.Repo") as mock_repo:
        # Mock environment variable not set
        mock_getenv.return_value = "unknown"
        
        # Mock git repo and commit hash
        mock_head = MagicMock()
        mock_head.object.hexsha = "abcdef1234567890"
        mock_repo.return_value.head = mock_head
        
        response = client.get("/api/version")
        
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "unknown"
        assert data["git_commit"] == "abcdef1"

def test_get_version_git_error(client):
    """Test version endpoint when git repo access fails"""
    with patch("app.routers.version.os.getenv") as mock_getenv, \
         patch("app.routers.version.Repo") as mock_repo:
        # Mock environment variable
        mock_getenv.return_value = "1.0.0"
        
        # Mock git repo error
        mock_repo.side_effect = InvalidGitRepositoryError()
        
        response = client.get("/api/version")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data  # Error message should be in response
