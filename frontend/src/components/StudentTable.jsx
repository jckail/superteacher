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
  Paper
} from '@mui/material';
import config from '../config';

function StudentTable({ students, onStudentUpdate }) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);
  const [openGradeDialog, setOpenGradeDialog] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
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

      const createdStudent = await response.json();
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
      [name]: value
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

  return (
    <div>
      <Button
        variant="contained"
        color="primary"
        onClick={() => setOpenDialog(true)}
        style={{ marginBottom: '20px' }}
      >
        Add New Student
      </Button>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Class ID</TableCell>
              <TableCell>Section</TableCell>
              <TableCell>Student ID</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Academic Performance</TableCell>
              <TableCell>Tests</TableCell>
              <TableCell>Homework</TableCell>
              <TableCell>Attendance</TableCell>
              <TableCell>AI Insights</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {students.map((student) => (
              <TableRow key={student.id}>
                <TableCell>{student.class_id}</TableCell>
                <TableCell>{student.section}</TableCell>
                <TableCell>{student.id}</TableCell>
                <TableCell>{student.name}</TableCell>
                <TableCell>
                  <div>Rank: {student.academic_performance.rank}</div>
                  <div>GPA: {student.gpa}</div>
                </TableCell>
                <TableCell>
                  {Object.entries(student.academic_performance.tests || {}).map(([subject, score]) => (
                    <div key={subject}>
                      {subject}: {score}
                    </div>
                  ))}
                </TableCell>
                <TableCell>
                  <div>Points: {student.homework_points}</div>
                  <div>Completed: {student.homework_completed}</div>
                  {Object.entries(student.academic_performance.homework || {}).map(([name, score]) => (
                    <div key={name}>
                      {name}: {score}
                    </div>
                  ))}
                </TableCell>
                <TableCell>
                  <div>{student.attendance_percentage}%</div>
                  <div>{student.attendance_days}</div>
                </TableCell>
                <TableCell>
                  <div>Status: {student.ai_insights.status}</div>
                  <div>{student.ai_insights.recommendation}</div>
                </TableCell>
                <TableCell>
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={() => handleAddGrade(student)}
                    disabled={isSubmitting}
                  >
                    Add Grade
                  </Button>
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
          <TextField
            margin="dense"
            name="class_id"
            label="Class ID"
            type="text"
            fullWidth
            value={newStudent.class_id}
            onChange={handleInputChange}
          />
          <TextField
            margin="dense"
            name="section"
            label="Section"
            type="text"
            fullWidth
            value={newStudent.section}
            onChange={handleInputChange}
          />
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
    </div>
  );
}

export default StudentTable;
