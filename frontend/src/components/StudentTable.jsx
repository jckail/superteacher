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
  styled,
  Tooltip,
  Divider
} from '@mui/material';
import config from '../config';
import { useNotification } from '../contexts/NotificationContext';

// Styled Components
const StyledTableContainer = styled(TableContainer)({
  position: 'relative',
  height: '100%',
  '& table': {
    borderCollapse: 'separate',
    borderSpacing: 0,
  }
});

const StyledTableHead = styled(TableHead)({
  position: 'sticky',
  top: 0,
  zIndex: 1000,
  backgroundColor: '#f3f0ff',
  '& th': {
    borderBottom: '2px solid #e9ecef',
  }
});

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

const ScoreCard = styled(Box)({
  backgroundColor: '#f8fafc',
  borderRadius: '4px',
  padding: '6px',
  marginBottom: '4px',
  border: '1px solid #e2e8f0',
});

function StudentTable({ students, classes, sections, onStudentUpdate }) {
  const { showNotification } = useNotification();
  const [isSubmitting, setIsSubmitting] = useState(false);
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

  const handleContactParent = (student) => {
    showNotification('Parent contact feature coming soon!');
  };

  const handleAddEvent = (student) => {
    showNotification('Event scheduling feature coming soon!');
  };

  const handleEscalate = (student) => {
    showNotification('Issue escalation feature coming soon!');
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

  const getStatusIcon = (status) => {
    switch (status.toLowerCase()) {
      case 'outstanding':
      case 'excellent':
        return '🌟';
      case 'very good':
      case 'good':
        return '✨';
      case 'fair':
        return '⚠️';
      case 'needs improvement':
      case 'at risk':
        return '❗';
      default:
        return '📊';
    }
  };

  return (
    <StyledTableContainer>
      <Table stickyHeader>
        <StyledTableHead>
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
        </StyledTableHead>
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
                    GPA: {student.gpa.toFixed(1)}
                  </StatusBadge>
                  <Typography variant="body2" color="textSecondary">
                    Rank: {student.academic_performance.rank}
                  </Typography>
                </Box>
              </TableCell>
              <TableCell>
                <Box sx={{ maxHeight: 200, overflowY: 'auto' }}>
                  {student.academic_performance.tests && Object.entries(student.academic_performance.tests).map(([testName, score]) => (
                    <ScoreCard key={testName}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {testName}
                      </Typography>
                      <Typography variant="body2" color={parseInt(score) >= 70 ? 'success.main' : 'error.main'}>
                        {score}
                      </Typography>
                    </ScoreCard>
                  ))}
                </Box>
              </TableCell>
              <TableCell>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <Typography variant="body2">
                    Points: {student.homework_points}
                  </Typography>
                  <Typography variant="body2">
                    Completed: {student.homework_completed}
                  </Typography>
                  {student.academic_performance.homework && (
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        Recent Assignments:
                      </Typography>
                      {Object.entries(student.academic_performance.homework).map(([name, score]) => (
                        <ScoreCard key={name}>
                          <Typography variant="body2">{name}: {score}</Typography>
                        </ScoreCard>
                      ))}
                    </Box>
                  )}
                </Box>
              </TableCell>
              <TableCell>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <StatusBadge status={getAttendanceStatus(student.attendance_percentage)}>
                    {student.attendance_percentage.toFixed(1)}%
                  </StatusBadge>
                  <Typography variant="body2" color="textSecondary">
                    {student.attendance_days}
                  </Typography>
                </Box>
              </TableCell>
              <TableCell>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <StatusBadge 
                    status={student.ai_insights.status.toLowerCase().includes('outstanding') || 
                           student.ai_insights.status.toLowerCase().includes('excellent') ? 'good' : 
                           student.ai_insights.status.toLowerCase().includes('good') ? 'warning' : 'danger'}
                  >
                    {getStatusIcon(student.ai_insights.status)} {student.ai_insights.status}
                  </StatusBadge>
                  
                  {student.ai_insights.performance_breakdown && (
                    <Box sx={{ bgcolor: '#f8fafc', p: 1, borderRadius: '4px' }}>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>Performance:</Typography>
                      <Typography variant="body2">
                        Academic: {student.ai_insights.performance_breakdown.academic_strength}
                      </Typography>
                      <Typography variant="body2">
                        Attendance: {student.ai_insights.performance_breakdown.attendance_impact}
                      </Typography>
                      <Typography variant="body2">
                        Homework: {student.ai_insights.performance_breakdown.homework_consistency}
                      </Typography>
                    </Box>
                  )}
                  
                  <Tooltip title={student.ai_insights.recommendation} arrow>
                    <Typography 
                      variant="body2" 
                      color="textSecondary"
                      sx={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        cursor: 'pointer'
                      }}
                    >
                      {student.ai_insights.recommendation}
                    </Typography>
                  </Tooltip>
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
                    onClick={() => handleContactParent(student)}
                  >
                    Contact Parent
                  </ActionButton>
                  <ActionButton
                    variant="contained"
                    color="success"
                    size="small"
                    onClick={() => handleAddEvent(student)}
                  >
                    Add Event
                  </ActionButton>
                  <ActionButton
                    variant="contained"
                    color="warning"
                    size="small"
                    onClick={() => handleEscalate(student)}
                  >
                    Escalate
                  </ActionButton>
                </Box>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

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
    </StyledTableContainer>
  );
}

export default StudentTable;
