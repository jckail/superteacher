from pydantic import BaseModel
from typing import Dict, Optional, Literal, List

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
    academic_performance: Dict
    ai_insights: Dict

    class Config:
        orm_mode = True

class Grade(BaseModel):
    testName: str
    score: int
    totalPoints: int
    date: str
    gradeType: Literal["homework", "test"]

class Class(BaseModel):
    id: str
    name: str

class ClassResponse(BaseModel):
    classes: List[Class]

class Section(BaseModel):
    name: str
    class_id: str

class SectionResponse(BaseModel):
    sections: List[Dict[str, str]]  # List of {name: str, class_id: str}
