# Super Teacher Frontend

The frontend of Super Teacher is built with React and Material-UI, providing a modern and intuitive interface for teachers to manage their classrooms and leverage AI assistance.

## Architecture

### Key Components
- **Dashboard**: Main interface for classroom management and overview
- **Student Management**: Detailed student profiles and performance tracking
- **Chat Interface**: AI-powered assistant for teaching support
- **Progress Reports**: Visual representation of student progress
- **Grade Management**: Interface for managing and analyzing student grades

### Directory Structure
```
frontend/
├── src/
│   ├── components/         # Reusable React components
│   │   ├── dashboard/     # Dashboard-specific components
│   │   ├── student/       # Student management components
│   │   └── Chat.jsx       # AI chat interface
│   ├── contexts/          # React Context providers
│   ├── pages/             # Main page components
│   └── utils/             # Utility functions and helpers
├── public/                # Static assets
└── package.json          # Project dependencies and scripts
```

## Setup and Development

### Prerequisites
- Node.js (v14 or higher)
- npm or yarn package manager

### Installation
1. Install dependencies:
```bash
npm install
```

2. Configure environment:
Create a `.env` file in the frontend directory:
```env
VITE_API_URL=http://localhost:8000
```

3. Start development server:
```bash
npm run dev
```

The application will be available at http://localhost:5173

### Available Scripts
- `npm run dev`: Start development server
- `npm run build`: Build for production
- `npm run preview`: Preview production build
- `npm run lint`: Run ESLint
- `npm test`: Run tests

## Component Documentation

### Dashboard
The main interface where teachers can:
- View all their class sections
- Monitor student progress
- Access quick actions
- View AI-generated insights

### Student Management
Provides functionality for:
- Adding/editing student information
- Recording grades
- Viewing performance history
- Generating AI insights for individual students

### Chat Interface
AI-powered assistant that helps with:
- Lesson planning
- Student engagement strategies
- Classroom management advice
- Educational resource recommendations

## State Management
- React Context API for global state
- Local component state for UI-specific data
- Notification system for user feedback

## API Integration
- Axios for HTTP requests
- Centralized API configuration
- Error handling and retry logic
- Request/response interceptors

## Best Practices
- Component composition for reusability
- Proper error boundary implementation
- Performance optimization using React.memo and useMemo
- Consistent error handling and loading states
- Responsive design principles
- Accessibility compliance

## Contributing
1. Follow the existing code style
2. Write meaningful commit messages
3. Document new components and features
4. Add appropriate test coverage
5. Submit pull requests for review
