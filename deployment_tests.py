import os
import sys
import pytest
import requests
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_base_url():
    # Wait longer for container to be ready (up to 30 seconds)
    base_url = os.getenv('TEST_URL', 'http://localhost:8080')
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f"{base_url}/api/health")
            if response.status_code == 200:
                logger.info("✅ Server is ready")
                return base_url
        except requests.exceptions.ConnectionError:
            pass
        logger.info(f"⏳ Waiting for server to be ready... ({i+1}/{max_retries})")
        time.sleep(1)
    raise Exception("Server failed to become ready")

def test_health_endpoint():
    """Test the health check endpoint"""
    response = requests.get(f"{get_base_url()}/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "details" in data
    assert "database" in data["details"]
    assert "server" in data["details"]

def test_version_endpoint():
    """Test the version endpoint"""
    response = requests.get(f"{get_base_url()}/api/version")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "git_commit" in data

def test_get_students():
    """Test getting all students"""
    response = requests.get(f"{get_base_url()}/api/db/students")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_and_get_student():
    """Test creating a new student and then retrieving it"""
    # Create a new student
    student_data = {
        "name": "Test Student",
        "grade": "10",
        "class_id": "C1001",
        "section": "A"
    }
    response = requests.post(f"{get_base_url()}/api/db/students", json=student_data)
    assert response.status_code == 200
    new_student = response.json()
    assert "id" in new_student

    # Get the created student
    student_id = new_student["id"]
    response = requests.get(f"{get_base_url()}/api/db/students/{student_id}")
    assert response.status_code == 200
    retrieved_student = response.json()
    assert retrieved_student["name"] == student_data["name"]

def test_get_students_by_class():
    """Test getting students by class"""
    class_id = "C1001"  # Using the same class_id from previous test
    response = requests.get(f"{get_base_url()}/api/db/classes/{class_id}/students")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_add_grade():
    """Test adding a grade to a student"""
    # First create a student
    student_data = {
        "name": "Grade Test Student",
        "grade": "10",
        "class_id": "C1002",
        "section": "B"
    }
    response = requests.post(f"{get_base_url()}/api/db/students", json=student_data)
    assert response.status_code == 200
    student_id = response.json()["id"]

    # Add a grade
    grade_data = {
        "testName": "Math Test 1",
        "score": 85,
        "totalPoints": 100
    }
    response = requests.post(
        f"{get_base_url()}/api/db/students/{student_id}/grades",
        json=grade_data
    )
    assert response.status_code == 200
    updated_student = response.json()
    assert "academic_performance" in updated_student
    assert "tests" in updated_student["academic_performance"]
    assert "Math Test 1" in updated_student["academic_performance"]["tests"]

def run_tests():
    """Run the deployment tests and return success status"""
    logger.info("Starting deployment tests...")
    try:
        # Run tests and capture the result
        exit_code = pytest.main([__file__, "-v"])
        
        if exit_code == 0:
            logger.info("✅ All deployment tests passed successfully!")
            print("DEPLOYMENT_TESTS_SUCCEEDED=true")
            return True
        else:
            logger.error("❌ Deployment tests failed!")
            print("DEPLOYMENT_TESTS_SUCCEEDED=false")
            return False
    except Exception as e:
        logger.error(f"❌ Error running deployment tests: {str(e)}")
        print("DEPLOYMENT_TESTS_SUCCEEDED=false")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
