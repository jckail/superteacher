# Super Teacher Backend

The backend of Super Teacher is built with FastAPI, providing a robust and scalable API to support AI-enhanced teaching capabilities and classroom management.

## Architecture

### Core Components
- **FastAPI Application**: High-performance async web framework
- **SQLAlchemy ORM**: Database interactions and models
- **Pydantic Schemas**: Request/response validation
- **AI Integration**: Custom AI models and external API integrations

### Directory Structure
```
backend/
├── app/
│   ├── models/           # SQLAlchemy models
│   ├── routers/          # API route handlers
│   ├── schemas/          # Pydantic schemas
│   └── __init__.py
├── tests/               # Test suite
├── main.py             # Application entry point
└── requirements.txt    # Python dependencies
```

## Setup and Development

### Prerequisites
- Python 3.8 or higher
- pip package manager
- Virtual environment tool (venv or conda)

### Installation

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
Create a `.env` file in the backend directory:
```env
DATABASE_URL=sqlite:///./superteacher.db
SECRET_KEY=your_secret_key_here
AI_API_KEY=your_ai_api_key
```

4. Start development server:
```bash
uvicorn main:app --reload
```

The API will be available at http://localhost:8000

## API Documentation

### Available Endpoints

#### Chat Routes
- `POST /chat/message`: Send message to AI assistant
- `GET /chat/history`: Retrieve chat history

#### Student Management
- `GET /students`: List all students
- `POST /students`: Add new student
- `GET /students/{id}`: Get student details
- `PUT /students/{id}`: Update student information
- `DELETE /students/{id}`: Remove student

#### Grade Management
- `POST /grades`: Add new grade
- `GET /grades/student/{id}`: Get student grades
- `PUT /grades/{id}`: Update grade
- `DELETE /grades/{id}`: Remove grade

#### AI Insights
- `GET /insights/student/{id}`: Get AI insights for student
- `GET /insights/class/{id}`: Get AI insights for class

### Interactive Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Database

### Models
- Student
- Grade
- Section
- Teacher
- ChatHistory
- AIInsight

### Migrations
Using Alembic for database migrations:
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head
```

## Testing

### Running Tests
```bash
pytest
```

### Test Coverage
```bash
pytest --cov=app tests/
```

## AI Integration

### Features
- Natural language processing for chat
- Student performance analysis
- Personalized teaching recommendations
- Automated progress report generation

### Implementation
- Custom AI models for education-specific tasks
- Integration with external AI APIs
- Caching system for optimization
- Rate limiting and usage tracking

## Security

### Implemented Measures
- JWT authentication
- Role-based access control
- Input validation
- SQL injection prevention
- Rate limiting
- CORS configuration

## Performance Optimization

- Database query optimization
- Response caching
- Async operations
- Connection pooling
- Resource monitoring

## Contributing
1. Follow PEP 8 style guide
2. Write unit tests for new features
3. Update API documentation
4. Use type hints
5. Handle errors appropriately
