from sqlalchemy import create_engine, Column, Integer, String, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Create SQLite database URL
SQLALCHEMY_DATABASE_URL = "sqlite:///./schooltool.db"

# Create SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Define Student model
class Student(Base):
    __tablename__ = "students"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)
    class_id = Column(String, nullable=False)
    section = Column(String, nullable=False)
    gpa = Column(Float, default=0.0)
    attendance_percentage = Column(Float, default=100.0)
    attendance_days = Column(String, default="0/0")
    homework_points = Column(Integer, default=0)
    homework_completed = Column(String, default="0/0")
    academic_performance = Column(JSON, default=lambda: {"rank": "New Student", "tests": {}})
    ai_insights = Column(JSON, default=lambda: {
        "status": "Pending",
        "recommendation": "Initial assessment needed"
    })

# Create the database tables
def init_db():
    Base.metadata.create_all(bind=engine)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
