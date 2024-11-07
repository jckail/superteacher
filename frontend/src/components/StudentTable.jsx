import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Box,
  Typography,
  Paper,
  styled
} from '@mui/material';
import config from '../config';

// Styled Components
const StyledTableCell = styled(TableCell)(({ theme }) => ({
  backgroundColor: '#f3f0ff',
  padding: '12px 16px',
  fontWeight: 500,
  color: '#374151',
  borderBottom: '1px solid #e9ecef',
  '&.sortable': {
    cursor: 'pointer',
    position: 'relative',
    paddingRight: '24px',
    
    '&::after': {
      content: '"↕"',
      position: 'absolute',
      right: '8px',
      top: '50%',
      transform: 'translateY(-50%)',
      fontSize: '12px',
      opacity: 0.5,
    },
    
    '&.sorted-asc::after': {
      content: '"▲"',
      opacity: 1,
    },
    
    '&.sorted-desc::after': {
      content: '"▼"',
      opacity: 1,
    }
  }
}));

const StatusBadge = styled(Box)(({ status }) => ({
  padding: '4px 8px',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 500,
  display: 'inline-block',
  ...(status === 'good' && {
    background: '#dcfce7',
    color: '#166534',
  }),
  ...(status === 'warning' && {
    background: '#fef3c7',
    color: '#92400e',
  }),
  ...(status === 'danger' && {
    background: '#fee2e2',
    color: '#991b1b',
  }),
}));

const ClassBadge = styled(Box)({
  background: '#f3f0ff',
  color: '#7e3af2',
  padding: '2px 8px',
  borderRadius: '4px',
  fontSize: '12px',
  fontWeight: 500,
  display: 'inline-block',
});

const ActionButton = styled(Button)({
  width: '100%',
  marginBottom: '8px',
  textTransform: 'none',
});

function StudentTable({ students, classes, sections, onStudentUpdate }) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);
  const [openGradeDialog, setOpenGradeDialog] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [newGrade, setNewGrade] = useState({
    testName: '',
    score: '',
    totalPoints: '',
    date: new Date().toISOString().split('T')[0],
    gradeType: 'test'
  });
  const [newStudent, setNewStudent] = useState({
    name: '',
    grade: '',
    class_id: '',
    section: ''
  });

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const sortedStudents = React.useMemo(() => {
    if (!sortConfig.key) return students;

    return [...students].sort((a, b) => {
      if (a[sortConfig.key] < b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (a[sortConfig.key] > b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });
  }, [students, sortConfig]);

  const handleAddStudent = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/students`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newStudent),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      setOpenDialog(false);
      setNewStudent({
        name: '',
        grade: '',
        class_id: '',
        section: ''
      });
      onStudentUpdate();
    } catch (error) {
      console.error('Error adding student:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setNewStudent(prev => ({
      ...prev,
      [name]: value,
      ...(name === 'class_id' ? { section: '' } : {})
    }));
  };

  const handleGradeInputChange = (e) => {
    const { name, value } = e.target;
    setNewGrade(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleAddGrade = async (student) => {
    setSelectedStudent(student);
    setOpenGradeDialog(true);
  };

  const handleSubmitGrade = async () => {
    setIsSubmitting(true);
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/students/${selectedStudent.id}/grades`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newGrade),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      setOpenGradeDialog(false);
      setNewGrade({
        testName: '',
        score: '',
        totalPoints: '',
        date: new Date().toISOString().split('T')[0],
        gradeType: 'test'
      });
      onStudentUpdate();
    } catch (error) {
      console.error('Error adding grade:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getGpaStatus = (gpa) => {
    if (gpa >= 3.5) return 'good';
    if (gpa >= 2.5) return 'warning';
    return 'danger';
  };

  const getAttendanceStatus = (percentage) => {
    if (percentage >= 90) return 'good';
    if (percentage >= 80) return 'warning';
    return 'danger';
  };

  return (
    <Paper elevation={1} sx={{ margin: 2, borderRadius: 2, overflow: 'hidden' }}>
      <Button
        variant="contained"
        color="primary"
        onClick={() => setOpenDialog(true)}
        sx={{ margin: 2 }}
      >
        Add New Student
      </Button>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <StyledTableCell 
                className={`sortable ${sortConfig.key === 'class_id' ? `sorted-${sortConfig.direction}` : ''}`}
                onClick={() => handleSort('class_id')}
              >
                Class ID
              </StyledTableCell>
              <StyledTableCell 
                className={`sortable ${sortConfig.key === 'section' ? `sorted-${sortConfig.direction}` : ''}`}
                onClick={() => handleSort('section')}
              >
                Section
              </StyledTableCell>
              <StyledTableCell 
                className={`sortable ${sortConfig.key === 'id' ? `sorted-${sortConfig.direction}` : ''}`}
                onClick={() => handleSort('id')}
              >
                Student ID
              </StyledTableCell>
              <StyledTableCell 
                className={`sortable ${sortConfig.key === 'name' ? `sorted-${sortConfig.direction}` : ''}`}
                onClick={() => handleSort('name')}
              >
                Name
              </StyledTableCell>
              <StyledTableCell>Academic Performance</StyledTableCell>
              <StyledTableCell>Tests</StyledTableCell>
              <StyledTableCell>Homework</StyledTableCell>
              <StyledTableCell>Attendance</StyledTableCell>
              <StyledTableCell>AI Insights</StyledTableCell>
              <StyledTableCell>Actions</StyledTableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedStudents.map((student) => (
              <TableRow key={student.id} sx={{ '&:hover': { bgcolor: '#f8f7ff' } }}>
                <TableCell>
                  <ClassBadge>{student.class_id}</ClassBadge>
                </TableCell>
                <TableCell>
                  <ClassBadge>{student.section}</ClassBadge>
                </TableCell>
                <TableCell>{student.id}</TableCell>
                <TableCell>
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>{student.name}</Typography>
                  <Typography variant="body2" color="textSecondary">
                    Grade {student.grade || 'N/A'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <StatusBadge status={getGpaStatus(student.gpa)}>
                      GPA: {student.gpa}
                    </StatusBadge>
                    <Typography variant="body2" color="textSecondary">
                      Rank: {student.academic_performance.rank}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  {student.academic_performance.tests && Object.entries(student.academic_performance.tests).map(([testName, score]) => (
                    <Box key={testName} sx={{ mb: 1, p: 1, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                      <Typography variant="body2">
                        <strong>{testName}:</strong> {score}
                      </Typography>
                    </Box>
                  ))}
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <Typography variant="body2">
                      Points: {student.homework_points}
                    </Typography>
                    <Typography variant="body2">
                      Completed: {student.homework_completed}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <StatusBadge status={getAttendanceStatus(student.attendance_percentage)}>
                      {student.attendance_percentage}%
                    </StatusBadge>
                    <Typography variant="body2" color="textSecondary">
                      {student.attendance_days}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <StatusBadge status={student.ai_insights.status === 'Excellent' ? 'good' : 'warning'}>
                      {student.ai_insights.status === 'Excellent' ? '🎯' : '⚠️'} {student.ai_insights.status}
                    </StatusBadge>
                    <Typography variant="body2" color="textSecondary">
                      {student.ai_insights.recommendation}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 140 }}>
                    <ActionButton
                      variant="contained"
                      color="primary"
                      size="small"
                      onClick={() => handleAddGrade(student)}
                      disabled={isSubmitting}
                    >
                      Add Grade
                    </ActionButton>
                    <ActionButton
                      variant="contained"
                      color="error"
                      size="small"
                    >
                      Contact Parent
                    </ActionButton>
                    <ActionButton
                      variant="contained"
                      color="success"
                      size="small"
                    >
                      Add Event
                    </ActionButton>
                    <ActionButton
                      variant="contained"
                      color="warning"
                      size="small"
                    >
                      Escalate
                    </ActionButton>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
        <DialogTitle>Add New Student</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            name="name"
            label="Name"
            type="text"
            fullWidth
            value={newStudent.name}
            onChange={handleInputChange}
          />
          <TextField
            margin="dense"
            name="grade"
            label="Grade"
            type="number"
            fullWidth
            value={newStudent.grade}
            onChange={handleInputChange}
          />
          <FormControl fullWidth margin="dense">
            <InputLabel>Class</InputLabel>
            <Select
              name="class_id"
              value={newStudent.class_id}
              onChange={handleInputChange}
            >
              {classes.map((cls) => (
                <MenuItem key={cls.id} value={cls.id}>
                  {cls.name} ({cls.id})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth margin="dense">
            <InputLabel>Section</InputLabel>
            <Select
              name="section"
              value={newStudent.section}
              onChange={handleInputChange}
              disabled={!newStudent.class_id}
            >
              {newStudent.class_id && sections[newStudent.class_id]?.map((section) => (
                <MenuItem key={section.name} value={section.name}>
                  {section.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)} color="primary">
            Cancel
          </Button>
          <Button onClick={handleAddStudent} color="primary" disabled={isSubmitting}>
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={openGradeDialog} onClose={() => setOpenGradeDialog(false)}>
        <DialogTitle>Add Grade for {selectedStudent?.name}</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="dense">
            <InputLabel>Grade Type</InputLabel>
            <Select
              name="gradeType"
              value={newGrade.gradeType}
              onChange={handleGradeInputChange}
            >
              <MenuItem value="test">Test</MenuItem>
              <MenuItem value="homework">Homework</MenuItem>
            </Select>
          </FormControl>
          <TextField
            autoFocus
            margin="dense"
            name="testName"
            label={newGrade.gradeType === 'test' ? "Test Name" : "Homework Name"}
            type="text"
            fullWidth
            value={newGrade.testName}
            onChange={handleGradeInputChange}
          />
          <TextField
            margin="dense"
            name="score"
            label="Score"
            type="number"
            fullWidth
            value={newGrade.score}
            onChange={handleGradeInputChange}
          />
          <TextField
            margin="dense"
            name="totalPoints"
            label="Total Points"
            type="number"
            fullWidth
            value={newGrade.totalPoints}
            onChange={handleGradeInputChange}
          />
          <TextField
            margin="dense"
            name="date"
            label="Date"
            type="date"
            fullWidth
            value={newGrade.date}
            onChange={handleGradeInputChange}
            InputLabelProps={{
              shrink: true,
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenGradeDialog(false)} color="primary">
            Cancel
          </Button>
          <Button onClick={handleSubmitGrade} color="primary" disabled={isSubmitting}>
            Add Grade
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}

export default StudentTable;
