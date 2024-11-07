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
  Paper
} from '@mui/material';
import config from '../config';

function StudentTable({ students, onStudentUpdate }) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);
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
      const response = await fetch(`${config.apiBaseUrl}/students`, {
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

  const handleAddGrade = async (selectedStudent) => {
    const grade = {
      testName: "Test 3",
      score: 85,
      totalPoints: 100,
      date: new Date().toISOString()
    };

    setIsSubmitting(true);
    try {
      const response = await fetch(`${config.apiBaseUrl}/students/${selectedStudent.id}/grades`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(grade),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

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
              <TableCell>Attendance</TableCell>
              <TableCell>Homework</TableCell>
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
                  <div>{student.attendance_percentage}%</div>
                  <div>{student.attendance_days}</div>
                </TableCell>
                <TableCell>
                  <div>Points: {student.homework_points}</div>
                  <div>Completed: {student.homework_completed}</div>
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
    </div>
  );
}

export default StudentTable;
