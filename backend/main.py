from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app.models.database import Student as DBStudent, get_db, init_db

# Initialize database before creating FastAPI app
init_db()

app = FastAPI(title="EduTrack Pro API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class StudentBase(BaseModel):
    name: str
    grade: int
    class_id: str
    section: str

class StudentCreate(StudentBase):
    pass

class Student(StudentBase):
    id: str
    gpa: float
    attendance_percentage: float
    attendance_days: str
    homework_points: int
    homework_completed: str
    academic_performance: dict
    ai_insights: dict

    class Config:
        orm_mode = True

class Grade(BaseModel):
    testName: str
    score: int
    totalPoints: int
    date: str

# API endpoints
@app.get("/students", response_model=List[Student])
async def get_students(db: Session = Depends(get_db)):
    students = db.query(DBStudent).all()
    return students

@app.get("/students/{student_id}", response_model=Student)
async def get_student(student_id: str, db: Session = Depends(get_db)):
    student = db.query(DBStudent).filter(DBStudent.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student

@app.get("/classes/{class_id}/students", response_model=List[Student])
async def get_students_by_class(class_id: str, db: Session = Depends(get_db)):
    students = db.query(DBStudent).filter(DBStudent.class_id == class_id).all()
    return students

@app.post("/students", response_model=Student)
async def create_student(student: StudentCreate, db: Session = Depends(get_db)):
    # Generate new student ID
    student_count = db.query(DBStudent).count()
    new_id = f"ST{student_count + 1:04d}"
    
    # Create new student
    db_student = DBStudent(
        id=new_id,
        name=student.name,
        grade=student.grade,
        class_id=student.class_id,
        section=student.section
    )
    
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@app.post("/students/{student_id}/grades", response_model=Student)
async def add_grade(student_id: str, grade: Grade, db: Session = Depends(get_db)):
    student = db.query(DBStudent).filter(DBStudent.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Calculate percentage score
    percentage = round((grade.score / grade.totalPoints) * 100)
    
    # Update academic performance
    academic_performance = student.academic_performance
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
    student.gpa = new_gpa
    student.academic_performance = academic_performance
    
    db.commit()
    db.refresh(student)
    return student
