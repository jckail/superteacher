import React, { useState, useEffect } from 'react';
import StudentTable from '../components/StudentTable';
import { 
  Button, 
  Dialog, 
  DialogTitle, 
  DialogContent, 
  DialogActions, 
  TextField, 
  FormControl, 
  InputLabel, 
  Select, 
  MenuItem,
  Box,
  Paper,
  Typography,
  styled
} from '@mui/material';
import config from '../config';

const ProgressReportSection = styled(Box)(({ theme }) => ({
  padding: '16px 24px',
  background: '#f3f0ff',
  borderBottom: '1px solid #e9ecef',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}));

const ReportDates = styled(Box)({
  display: 'flex',
  gap: '24px',
  alignItems: 'center',
});

const DateLabel = styled(Typography)({
  fontSize: '14px',
  color: '#6b7280',
});

const DateValue = styled(Typography)({
  color: '#7e3af2',
  fontWeight: 500,
  cursor: 'pointer',
});

const Controls = styled(Box)(({ theme }) => ({
  padding: '16px 24px',
  display: 'flex',
  gap: '12px',
  alignItems: 'center',
  borderBottom: '1px solid #e9ecef',
}));

function Dashboard() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState({});
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [newSection, setNewSection] = useState({
    name: '',
    class_id: ''
  });

  useEffect(() => {
    fetchStudents();
    fetchClasses();
  }, []);

  const fetchStudents = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/students`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setStudents(data);
      setError(null);
    } catch (error) {
      console.error('Error fetching students:', error);
      setError('Failed to load students. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const fetchClasses = async () => {
    try {
      console.log('Fetching classes...');
      const response = await fetch(`${config.apiBaseUrl}/db/classes`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log('Classes data:', data);
      setClasses(data.classes);
      
      const sectionsMap = {};
      await Promise.all(data.classes.map(async (cls) => {
        console.log(`Fetching sections for class ${cls.id}...`);
        const sectionsResponse = await fetch(`${config.apiBaseUrl}/db/classes/${cls.id}/sections`);
        if (sectionsResponse.ok) {
          const sectionsData = await sectionsResponse.json();
          console.log(`Sections for class ${cls.id}:`, sectionsData);
          sectionsMap[cls.id] = sectionsData.sections;
        }
      }));
      setSections(sectionsMap);
    } catch (error) {
      console.error('Error fetching classes:', error);
    }
  };

  const handleAddSection = async () => {
    try {
      console.log('Adding new section:', newSection);
      const response = await fetch(`${config.apiBaseUrl}/db/sections`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newSection),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      setOpenDialog(false);
      setNewSection({ name: '', class_id: '' });
      fetchClasses();
    } catch (error) {
      console.error('Error adding section:', error);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    console.log(`Updating ${name} to ${value}`);
    setNewSection(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSearch = () => {
    // Filter students based on searchQuery
    // This would ideally be handled by the backend
    const filteredStudents = students.filter(student => 
      student.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      student.class_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      student.section.toLowerCase().includes(searchQuery.toLowerCase())
    );
    setStudents(filteredStudents);
  };

  const handleFetchMetadata = async () => {
    try {
      await fetchStudents();
      await fetchClasses();
    } catch (error) {
      console.error('Error fetching metadata:', error);
    }
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return <div className="error-message">{error}</div>;
  }

  return (
    <Paper elevation={1} sx={{ borderRadius: '12px', overflow: 'hidden' }}>
      <ProgressReportSection>
        <ReportDates>
          <Box>
            <DateLabel>Last Progress Report:</DateLabel>
            <DateValue component="a" href="#">Oct 15, 2024</DateValue>
          </Box>
          <Box>
            <DateLabel>Next Progress Report:</DateLabel>
            <DateValue>Dec 15, 2024</DateValue>
          </Box>
        </ReportDates>
        <Button variant="contained" color="primary">
          Generate Progress Report
        </Button>
      </ProgressReportSection>

      <Controls>
        <TextField
          placeholder="Search students, classes, or tests..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ flex: 1, maxWidth: '400px' }}
        />
        <Button variant="contained" color="primary" onClick={handleSearch}>
          Search
        </Button>
        <Button variant="contained" color="primary" onClick={handleFetchMetadata}>
          Fetch Metadata
        </Button>
        <Button
          variant="contained"
          color="primary"
          onClick={() => setOpenDialog(true)}
        >
          Add New Section
        </Button>
      </Controls>

      <StudentTable 
        students={students} 
        classes={classes}
        sections={sections}
        onStudentUpdate={fetchStudents} 
      />

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>Add New Section</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="dense">
            <InputLabel>Class</InputLabel>
            <Select
              name="class_id"
              value={newSection.class_id}
              onChange={handleInputChange}
            >
              {classes.map((cls) => (
                <MenuItem key={cls.id} value={cls.id}>
                  {cls.name} ({cls.id})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            autoFocus
            margin="dense"
            name="name"
            label="Section Name"
            type="text"
            fullWidth
            value={newSection.name}
            onChange={handleInputChange}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)} color="primary">
            Cancel
          </Button>
          <Button 
            onClick={handleAddSection} 
            color="primary"
            disabled={!newSection.name || !newSection.class_id}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

export default Dashboard;
