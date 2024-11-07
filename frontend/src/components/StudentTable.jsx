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
  Divider,
  TablePagination,
  useMediaQuery,
  useTheme,
  Collapse,
  IconButton
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
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
  },
  [theme.breakpoints.down('sm')]: {
    padding: '8px 12px',
    fontSize: '0.875rem',
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

const ActionButton = styled(Button)(({ theme }) => ({
  width: '100%',
  marginBottom: '8px',
  textTransform: 'none',
  [theme.breakpoints.down('sm')]: {
    fontSize: '0.75rem',
    padding: '4px 8px',
  }
}));

const ScoreCard = styled(Box)(({ theme }) => ({
  backgroundColor: '#f8fafc',
  borderRadius: '4px',
  padding: '6px',
  marginBottom: '4px',
  border: '1px solid #e2e8f0',
  [theme.breakpoints.down('sm')]: {
    padding: '4px',
    marginBottom: '2px',
  }
}));

function Row({ student, handleAddGrade, handleContactParent, handleAddEvent, handleEscalate, isSubmitting }) {
  const [open, setOpen] = useState(false);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

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
    <>
      <TableRow>
        {!isMobile && (
          <>
            <TableCell>{student.class_id}</TableCell>
            <TableCell>{student.section}</TableCell>
          </>
        )}
        <TableCell>{student.id}</TableCell>
        <TableCell>{student.name}</TableCell>
        <TableCell>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <StatusBadge status={getGpaStatus(student.gpa)}>
              GPA: {student.gpa.toFixed(1)}
            </StatusBadge>
          </Box>
        </TableCell>
        {!isMobile ? (
          <>
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
              </Box>
            </TableCell>
          </>
        ) : (
          <TableCell>
            <IconButton
              aria-label="expand row"
              size="small"
              onClick={() => setOpen(!open)}
            >
              {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
            </IconButton>
          </TableCell>
        )}
        <TableCell>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: isMobile ? 100 : 140 }}>
            <ActionButton
              variant="contained"
              color="primary"
              size="small"
              onClick={() => handleAddGrade(student)}
              disabled={isSubmitting}
            >
              Add Grade
            </ActionButton>
            {!isMobile && (
              <>
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
              </>
            )}
          </Box>
        </TableCell>
      </TableRow>
      {isMobile && (
        <TableRow>
          <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={6}>
            <Collapse in={open} timeout="auto" unmountOnExit>
              <Box sx={{ margin: 1 }}>
                <Typography variant="h6" gutterBottom component="div">
                  Details
                </Typography>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">Tests</Typography>
                  {student.academic_performance.tests && Object.entries(student.academic_performance.tests).map(([testName, score]) => (
                    <ScoreCard key={testName}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {testName}: {score}
                      </Typography>
                    </ScoreCard>
                  ))}
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">Homework</Typography>
                  <Typography variant="body2">
                    Points: {student.homework_points}
                  </Typography>
                  <Typography variant="body2">
                    Completed: {student.homework_completed}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <ActionButton
                    variant="contained"
                    color="error"
                    size="small"
                    onClick={() => handleContactParent(student)}
                  >
                    Contact
                  </ActionButton>
                  <ActionButton
                    variant="contained"
                    color="success"
                    size="small"
                    onClick={() => handleAddEvent(student)}
                  >
                    Event
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
              </Box>
            </Collapse>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function StudentTable({ students, classes, sections, onStudentUpdate }) {
  const { showNotification } = useNotification();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openGradeDialog, setOpenGradeDialog] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
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

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const sortedStudents = React.useMemo(() => {
    if (!sortConfig.key) return students;

    return [...students].sort((a, b) => {
      // Special handling for GPA sorting
      if (sortConfig.key === 'gpa') {
        return sortConfig.direction === 'asc' 
          ? a.gpa - b.gpa
          : b.gpa - a.gpa;
      }

      // Handle string comparisons
      if (typeof a[sortConfig.key] === 'string') {
        const aValue = a[sortConfig.key].toLowerCase();
        const bValue = b[sortConfig.key].toLowerCase();
        if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      }

      // Handle numeric comparisons
      if (a[sortConfig.key] < b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (a[sortConfig.key] > b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });
  }, [students, sortConfig]);

  const paginatedStudents = sortedStudents.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

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

  return (
    <>
      <StyledTableContainer>
        <Table stickyHeader>
          <StyledTableHead>
            <TableRow>
              {!isMobile && (
                <>
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
                </>
              )}
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
              <StyledTableCell 
                className={`sortable ${sortConfig.key === 'gpa' ? `sorted-${sortConfig.direction}` : ''}`}
                onClick={() => handleSort('gpa')}
              >
                Performance
              </StyledTableCell>
              {!isMobile ? (
                <>
                  <StyledTableCell>Tests</StyledTableCell>
                  <StyledTableCell>Homework</StyledTableCell>
                </>
              ) : (
                <StyledTableCell>Details</StyledTableCell>
              )}
              <StyledTableCell>Actions</StyledTableCell>
            </TableRow>
          </StyledTableHead>
          <TableBody>
            {paginatedStudents.map((student) => (
              <Row
                key={student.id}
                student={student}
                handleAddGrade={handleAddGrade}
                handleContactParent={handleContactParent}
                handleAddEvent={handleAddEvent}
                handleEscalate={handleEscalate}
                isSubmitting={isSubmitting}
              />
            ))}
          </TableBody>
        </Table>
      </StyledTableContainer>

      <Dialog 
        open={openGradeDialog} 
        onClose={() => setOpenGradeDialog(false)}
        fullScreen={isMobile}
      >
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
    </>
  );
}

export default StudentTable;
