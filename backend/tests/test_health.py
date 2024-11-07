import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from unittest.mock import patch

def test_health_check_success(client):
    """Test health check endpoint when all systems are healthy"""
    with patch("app.routers.health.Session.execute") as mock_execute:
        mock_execute.return_value = True  # Simulate successful database connection
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "Database connection successful" in data["details"]["database"]
        assert "Server is running" in data["details"]["server"]

def test_health_check_db_failure(client):
    """Test health check endpoint when database is not responding"""
    # Mock the database execute to raise an exception
    with patch("app.routers.health.Session.execute") as mock_execute:
        mock_execute.side_effect = OperationalError("statement", "params", "orig")
        response = client.get("/api/health")
        
        assert response.status_code == 200  # Still returns 200 as the endpoint is accessible
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "Database error" in data["details"]["database"]
        assert "Server is running" in data["details"]["server"]
