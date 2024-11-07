import React, { useState } from 'react';
import {
  TableRow,
  TableCell,
  Box,
  Typography,
  IconButton,
  useTheme,
  useMediaQuery,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Grid,
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import { StatusBadge, ActionButton, ScoreCard } from './StyledComponents';
import AIInsightsBox from './AIInsightsBox';

const StudentTableRow = ({
  student,
  handleAddGrade,
  handleContactParent,
  handleAddEvent,
  handleEscalate,
  isSubmitting,
  columnWidths
}) => {
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

  const mobileRowStyle = {
    display: 'flex',
    width: '100%'
  };

  return (
    <>
      <TableRow sx={isMobile ? mobileRowStyle : undefined}>
        {!isMobile ? (
          <>
            <TableCell data-column="class_id" sx={{ width: columnWidths.class_id, minWidth: columnWidths.class_id }}>
              {student.class_id}
            </TableCell>
            <TableCell data-column="section" sx={{ width: columnWidths.section, minWidth: columnWidths.section }}>
              {student.section}
            </TableCell>
            <TableCell data-column="id" sx={{ width: columnWidths.id, minWidth: columnWidths.id }}>
              {student.id}
            </TableCell>
            <TableCell data-column="name" sx={{ width: columnWidths.name, minWidth: columnWidths.name }}>
              {student.name}
            </TableCell>
          </>
        ) : (
          <>
            <TableCell data-column="class-info" sx={{ flex: '0 0 25%' }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                  {student.class_id}
                </Typography>
                <Typography variant="body1" sx={{ fontSize: '0.875rem', fontWeight: 500 }}>
                  {student.section}
                </Typography>
              </Box>
            </TableCell>
            <TableCell data-column="student-info" sx={{ flex: '0 0 25%' }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.7rem' }}>
                  {student.id}
                </Typography>
                <Typography variant="body1" sx={{ fontSize: '0.875rem', fontWeight: 500 }}>
                  {student.name}
                </Typography>
              </Box>
            </TableCell>
          </>
        )}
        <TableCell data-column="performance" sx={isMobile ? { flex: '0 0 37.5%' } : { width: columnWidths.performance }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <StatusBadge status={getGpaStatus(student.gpa)}>
              GPA: {student.gpa.toFixed(1)}
            </StatusBadge>
          </Box>
        </TableCell>
        {!isMobile ? (
          <>
            <TableCell data-column="tests" sx={{ width: columnWidths.tests, minWidth: columnWidths.tests }}>
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
            <TableCell data-column="homework" sx={{ width: columnWidths.homework, minWidth: columnWidths.homework }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Typography variant="body2">
                  Points: {student.homework_points}
                </Typography>
                <Typography variant="body2">
                  Completed: {student.homework_completed}
                </Typography>
              </Box>
            </TableCell>
            <TableCell data-column="attendance" sx={{ width: columnWidths.attendance, minWidth: columnWidths.attendance }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <StatusBadge status={getAttendanceStatus(student.attendance_percentage)}>
                  {student.attendance_percentage.toFixed(1)}%
                </StatusBadge>
                <Typography variant="body2" color="textSecondary">
                  {student.attendance_days}
                </Typography>
              </Box>
            </TableCell>
            <TableCell data-column="insights" sx={{ width: columnWidths.insights, minWidth: columnWidths.insights }}>
              <AIInsightsBox insights={student.ai_insights} />
            </TableCell>
            <TableCell data-column="actions" sx={{ width: columnWidths.actions }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 140, alignItems: 'center' }}>
                <ActionButton
                  variant="contained"
                  color="success"
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
          </>
        ) : (
          <TableCell sx={{ flex: '0 0 12.5%', padding: '4px 2px', display: 'flex', justifyContent: 'center' }}>
            <IconButton
              aria-label="expand row"
              size="small"
              onClick={() => setOpen(true)}
              sx={{ color: 'success.main' }}
            >
              <Typography sx={{ fontSize: '1.5rem' }}>➕</Typography>
            </IconButton>
          </TableCell>
        )}
      </TableRow>
      {isMobile && (
        <Dialog
          open={open}
          onClose={() => setOpen(false)}
          fullWidth
          maxWidth="sm"
          PaperProps={{
            sx: {
              m: 1,
              maxHeight: 'calc(100% - 16px)'
            }
          }}
        >
          <DialogTitle>
            {student.name} - Details
          </DialogTitle>
          <DialogContent dividers>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Tests</Typography>
              <Box sx={{ maxHeight: '30vh', overflowY: 'auto' }}>
                {student.academic_performance.tests && Object.entries(student.academic_performance.tests).map(([testName, score]) => (
                  <ScoreCard key={testName}>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {testName}: {score}
                    </Typography>
                  </ScoreCard>
                ))}
              </Box>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Homework</Typography>
              <Typography variant="body2">
                Points: {student.homework_points}
              </Typography>
              <Typography variant="body2">
                Completed: {student.homework_completed}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>Attendance</Typography>
              <StatusBadge status={getAttendanceStatus(student.attendance_percentage)}>
                {student.attendance_percentage.toFixed(1)}%
              </StatusBadge>
              <Typography variant="body2" sx={{ mt: 1 }}>
                Days: {student.attendance_days}
              </Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>AI Insights</Typography>
              <AIInsightsBox insights={student.ai_insights} />
            </Box>
          </DialogContent>
          <DialogActions sx={{ p: 2, flexDirection: 'column' }}>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <ActionButton
                  variant="contained"
                  color="success"
                  size="small"
                  onClick={() => {
                    handleAddGrade(student);
                    setOpen(false);
                  }}
                  disabled={isSubmitting}
                  fullWidth
                >
                  Add Grade
                </ActionButton>
              </Grid>
              <Grid item xs={6}>
                <ActionButton
                  variant="contained"
                  color="error"
                  size="small"
                  onClick={() => {
                    handleContactParent(student);
                    setOpen(false);
                  }}
                  fullWidth
                >
                  Contact
                </ActionButton>
              </Grid>
              <Grid item xs={6}>
                <ActionButton
                  variant="contained"
                  color="success"
                  size="small"
                  onClick={() => {
                    handleAddEvent(student);
                    setOpen(false);
                  }}
                  fullWidth
                >
                  Event
                </ActionButton>
              </Grid>
              <Grid item xs={6}>
                <ActionButton
                  variant="contained"
                  color="warning"
                  size="small"
                  onClick={() => {
                    handleEscalate(student);
                    setOpen(false);
                  }}
                  fullWidth
                >
                  Escalate
                </ActionButton>
              </Grid>
            </Grid>
            <Button 
              onClick={() => setOpen(false)}
              sx={{ mt: 2 }}
            >
              Close
            </Button>
          </DialogActions>
        </Dialog>
      )}
    </>
  );
};

export default StudentTableRow;
