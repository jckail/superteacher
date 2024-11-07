import React, { useState } from 'react';
import { Paper } from '@mui/material';
import { TableContainer } from '../components/dashboard/StyledComponents';
import StudentTable from '../components/student/StudentTable';
import ProgressReport from '../components/dashboard/ProgressReport';
import SearchControls from '../components/dashboard/SearchControls';
import AddSectionDialog from '../components/dashboard/AddSectionDialog';
import AddStudentDialog from '../components/dashboard/AddStudentDialog';
import useStudentData from '../components/dashboard/hooks/useStudentData';

const initialSectionState = {
  name: '',
  class_id: ''
};

const initialStudentState = {
  name: '',
  grade: '',
  class_id: '',
  section: ''
};

function Dashboard() {
  const {
    students,
    setStudents,
    classes,
    sections,
    error,
    loading,
    addSection,
    addStudent,
    filterStudents
  } = useStudentData();

  const [searchQuery, setSearchQuery] = useState('');
  const [openSectionDialog, setOpenSectionDialog] = useState(false);
  const [openStudentDialog, setOpenStudentDialog] = useState(false);
  const [newSection, setNewSection] = useState(initialSectionState);
  const [newStudent, setNewStudent] = useState(initialStudentState);

  const handleInputChange = (e, type) => {
    const { name, value } = e.target;
    if (type === 'section') {
      setNewSection(prev => ({
        ...prev,
        [name]: value
      }));
    } else {
      setNewStudent(prev => ({
        ...prev,
        [name]: value,
        ...(name === 'class_id' ? { section: '' } : {})
      }));
    }
  };

  const handleSearch = () => {
    const filteredStudents = filterStudents(searchQuery);
    setStudents(filteredStudents);
  };

  const handleAddSection = async () => {
    const success = await addSection(newSection);
    if (success) {
      setOpenSectionDialog(false);
      setNewSection(initialSectionState);
    }
  };

  const handleAddStudent = async () => {
    const success = await addStudent(newStudent);
    if (success) {
      setOpenStudentDialog(false);
      setNewStudent(initialStudentState);
    }
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return <div className="error-message">{error}</div>;
  }

  return (
    <Paper 
      elevation={1} 
      sx={{ 
        borderRadius: '12px', 
        overflow: 'hidden', 
        height: '100vh',
        maxWidth: '100%',
        width: '100%'
      }}
    >
      <ProgressReport />
      
      <SearchControls
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearch={handleSearch}
        onAddStudent={() => setOpenStudentDialog(true)}
        onAddSection={() => setOpenSectionDialog(true)}
      />

      <TableContainer sx={{ maxWidth: '100%', width: '100%' }}>
        <StudentTable 
          students={students} 
          classes={classes}
          sections={sections}
          onStudentUpdate={filterStudents} 
        />
      </TableContainer>

      <AddSectionDialog
        open={openSectionDialog}
        onClose={() => setOpenSectionDialog(false)}
        classes={classes}
        newSection={newSection}
        onInputChange={handleInputChange}
        onSubmit={handleAddSection}
      />

      <AddStudentDialog
        open={openStudentDialog}
        onClose={() => setOpenStudentDialog(false)}
        classes={classes}
        sections={sections}
        newStudent={newStudent}
        onInputChange={handleInputChange}
        onSubmit={handleAddStudent}
      />
    </Paper>
  );
}

export default Dashboard;
