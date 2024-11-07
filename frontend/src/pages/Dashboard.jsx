import React, { useState, useEffect } from 'react';
import StudentTable from '../components/StudentTable';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import config from '../config';

function Dashboard() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState({});  // Map of class_id to sections
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(false);
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
      
      // Fetch sections for each class
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
      fetchClasses();  // Refresh classes and sections
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

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return <div className="error-message">{error}</div>;
  }

  return (
    <div>
      <Button
        variant="contained"
        color="primary"
        onClick={() => setOpenDialog(true)}
        style={{ marginBottom: '20px', marginRight: '20px' }}
      >
        Add New Section
      </Button>

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
    </div>
  );
}

export default Dashboard;
