from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Dict
import json
from ..schemas.student import Student, StudentCreate, Grade
from ..models.database import Student as DBStudent, get_db

router = APIRouter(
    prefix="/db",
    tags=["database"]
)

@router.get("/students", response_model=List[Student])
async def get_students(db: Session = Depends(get_db)):
    students = db.query(DBStudent).all()
    return students

@router.get("/students/{student_id}", response_model=Student)
async def get_student(student_id: str, db: Session = Depends(get_db)):
    student = db.query(DBStudent).filter(DBStudent.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student

@router.get("/classes/{class_id}/students", response_model=List[Student])
async def get_students_by_class(class_id: str, db: Session = Depends(get_db)):
    students = db.query(DBStudent).filter(DBStudent.class_id == class_id).all()
    return students

@router.post("/students", response_model=Student)
async def create_student(student: StudentCreate, db: Session = Depends(get_db)):
    # Generate new student ID
    student_count = db.query(DBStudent).count()
    new_id = f"ST{student_count + 1:04d}"
    
    # Initialize academic performance
    initial_academic_performance = {
        "rank": "New Student",
        "tests": {}
    }
    
    # Create new student with initialized fields
    db_student = DBStudent(
        id=new_id,
        name=student.name,
        grade=student.grade,
        class_id=student.class_id,
        section=student.section,
        gpa=0.0,
        attendance_percentage=100.0,
        attendance_days="0/0",
        homework_points=0,
        homework_completed="0/0",
        academic_performance=initial_academic_performance,
        ai_insights={"status": "Pending", "recommendation": "Initial assessment needed"}
    )
    
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.post("/students/{student_id}/grades", response_model=Student)
async def add_grade(student_id: str, grade: Grade, db: Session = Depends(get_db)):
    student = db.query(DBStudent).filter(DBStudent.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Calculate percentage score
    percentage = round((grade.score / grade.totalPoints) * 100)
    
    # Get current academic performance or initialize if None
    academic_performance = student.academic_performance
    if academic_performance is None:
        academic_performance = {"rank": "New Student", "tests": {}}
    elif isinstance(academic_performance, str):
        academic_performance = json.loads(academic_performance)
    
    # Ensure tests dictionary exists
    if "tests" not in academic_performance:
        academic_performance["tests"] = {}
    
    # Update tests dictionary
    academic_performance["tests"][grade.testName] = f"{percentage}%"
    
    # Recalculate GPA
    test_scores = [
        int(score.rstrip('%')) 
        for score in academic_performance["tests"].values()
    ]
    avg_score = sum(test_scores) / len(test_scores)
    new_gpa = round(avg_score / 25, 1)  # Convert percentage to 4.0 scale
    
    # Update rank based on new GPA
    if new_gpa >= 3.7:
        academic_performance["rank"] = "Top 5%"
    elif new_gpa >= 3.3:
        academic_performance["rank"] = "Top 10%"
    elif new_gpa >= 3.0:
        academic_performance["rank"] = "Top 25%"
    else:
        academic_performance["rank"] = "Average"
    
    # Update student record
    student.academic_performance = academic_performance
    student.gpa = new_gpa
    
    # Explicitly mark as modified
    db.add(student)
    db.commit()
    db.refresh(student)
    
    return student
