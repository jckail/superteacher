# SchoolTool

A full-stack web application for managing school-related tasks and information. The project consists of a React frontend with Material-UI components and a FastAPI backend with SQLite database.

## Tech Stack

### Frontend
- React 18
- Material-UI (MUI)
- React Router
- Axios for API calls

### Backend
- FastAPI
- SQLAlchemy
- SQLite
- Python 3.x

## Project Structure

```
schoolTool/
├── frontend/                # React frontend application
│   ├── public/             # Static files
│   ├── src/               
│   │   ├── components/     # Reusable React components
│   │   ├── pages/         # Page components
│   │   ├── utils/         # Utility functions
│   │   └── config.js      # Configuration file
│   └── package.json       # Frontend dependencies
│
└── backend/                # FastAPI backend application
    ├── app/
    │   ├── models/        # Database models
    │   ├── routers/       # API routes
    │   └── schemas/       # Pydantic schemas
    ├── main.py            # Application entry point
    └── requirements.txt   # Python dependencies
```

## Setup Instructions

### Backend Setup

1. Create a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. Run the backend server:
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at http://localhost:8000

### Frontend Setup

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Start the development server:
   ```bash
   npm start
   ```
   The application will be available at http://localhost:3000

## Available Scripts

### Frontend

- `npm start`: Runs the app in development mode
- `npm test`: Launches the test runner
- `npm run build`: Builds the app for production
- `npm run eject`: Ejects from create-react-app

### Backend

- Development server: `uvicorn main:app --reload`
- API documentation available at:
  - Swagger UI: http://localhost:8000/docs
  - ReDoc: http://localhost:8000/redoc

## Environment Variables

Create a `.env` file in the backend directory with the following variables:
```
SECRET_KEY=your_secret_key
DATABASE_URL=sqlite:///schooltool.db
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
