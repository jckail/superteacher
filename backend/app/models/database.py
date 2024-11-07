from sqlalchemy import create_engine, Column, Integer, String, Float, JSON, TypeDecorator, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create SQLite database URL with relative path
SQLALCHEMY_DATABASE_URL = "sqlite:///edutrack.db"
logger.info(f"Using database URL: {SQLALCHEMY_DATABASE_URL}")

# Create SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    json_serializer=lambda obj: json.dumps(obj),
    json_deserializer=lambda obj: json.loads(obj) if obj else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Custom JSON type for SQLite
class JSONType(TypeDecorator):
    impl = String
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return '{}'
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return {}
        return json.loads(value)

# Define Class model
class Class(Base):
    __tablename__ = "classes"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)

# Define Section model
class Section(Base):
    __tablename__ = "sections"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    class_id = Column(String, ForeignKey('classes.id'), nullable=False)

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
    academic_performance = Column(JSONType, default=lambda: {"rank": "New Student", "tests": {}})
    ai_insights = Column(JSONType, default=lambda: {
        "status": "Pending",
        "recommendation": "Initial assessment needed"
    })

# Create the database tables
def init_db():
    logger.info("Initializing database...")
    try:
        # Drop all tables first to ensure a clean state
        Base.metadata.drop_all(bind=engine)
        logger.info("Dropped existing tables")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Created database tables")
        
        # Only add sample data if we're not in a testing environment
        if not os.getenv("TESTING"):
            logger.info("Adding sample data...")
            db = SessionLocal()
            
            # Import here to avoid circular imports
            from .add_data import create_sample_data
            create_sample_data(db)
            
            logger.info("Sample data added successfully")
            db.close()
            
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
