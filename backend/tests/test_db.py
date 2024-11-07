import pytest
from fastapi.testclient import TestClient
from app.models.database import Student as DBStudent

@pytest.fixture
def sample_student():
    return {
        "name": "John Doe",
        "grade": 10,
        "class_id": "C1001",
        "section": "A"
    }

@pytest.fixture
def db_student(db_session):
    student = DBStudent(
        id="ST0001",
        name="Jane Smith",
        grade=10,
        class_id="C1001",
        section="A",
        gpa=3.5,
        attendance_percentage=95.0,
        attendance_days="19/20",
        homework_points=95,
        homework_completed="19/20",
        academic_performance={"tests": {}, "homework": {}, "rank": "Top 10%"},
        ai_insights={"strengths": [], "areas_for_improvement": []}
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student

@pytest.fixture(autouse=True)
def cleanup_database(db_session):
    # This fixture will run automatically before each test
    db_session.query(DBStudent).delete()
    db_session.commit()
    yield
    # And also after each test
    db_session.query(DBStudent).delete()
    db_session.commit()

def test_create_student(client, sample_student):
    """Test student creation"""
    response = client.post("/db/students", json=sample_student)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == sample_student["name"]
    assert data["grade"] == sample_student["grade"]
    assert data["class_id"] == sample_student["class_id"]
    assert data["section"] == sample_student["section"]
    assert data["id"].startswith("ST")
    assert isinstance(data["gpa"], float)
    assert isinstance(data["academic_performance"], dict)
    assert "tests" in data["academic_performance"]
    assert isinstance(data["academic_performance"]["tests"], dict)
    assert "homework" in data["academic_performance"]
    assert isinstance(data["academic_performance"]["homework"], dict)

def test_get_student_not_found(client):
    """Test getting a non-existent student"""
    response = client.get("/db/students/ST9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"

def test_get_students_by_class(client, db_student):
    """Test getting students by class"""
    response = client.get(f"/db/classes/{db_student.class_id}/students")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == db_student.id
    assert data[0]["class_id"] == db_student.class_id

def test_add_grade_student_not_found(client):
    """Test adding a grade to a non-existent student"""
    grade_data = {
        "testName": "Math Quiz 1",
        "score": 90,
        "totalPoints": 100,
        "date": "2024-02-20",
        "gradeType": "test"
    }
    
    response = client.post("/db/students/ST9999/grades", json=grade_data)
    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found"
