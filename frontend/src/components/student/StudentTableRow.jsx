import React, { useState } from 'react';
import {
  TableRow,
  TableCell,
  Box,
  Typography,
  IconButton,
  Collapse,
  useTheme,
  useMediaQuery,
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

  return (
    <>
      <TableRow>
        {!isMobile && (
          <>
            <TableCell data-column="class_id" sx={{ width: columnWidths.class_id, minWidth: columnWidths.class_id }}>
              {student.class_id}
            </TableCell>
            <TableCell data-column="section" sx={{ width: columnWidths.section, minWidth: columnWidths.section }}>
              {student.section}
            </TableCell>
          </>
        )}
        <TableCell data-column="id" sx={{ width: columnWidths.id, minWidth: columnWidths.id }}>
          {student.id}
        </TableCell>
        <TableCell data-column="name" sx={{ width: columnWidths.name, minWidth: columnWidths.name }}>
          {student.name}
        </TableCell>
        <TableCell data-column="performance" sx={{ width: columnWidths.performance, minWidth: columnWidths.performance }}>
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
          </>
        ) : (
          <TableCell data-column="details" sx={{ width: '40px', minWidth: '40px', padding: '4px' }}>
            <IconButton
              aria-label="expand row"
              size="small"
              onClick={() => setOpen(!open)}
            >
              {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
            </IconButton>
          </TableCell>
        )}
        <TableCell data-column="actions" sx={{ width: columnWidths.actions, minWidth: columnWidths.actions }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: isMobile ? 60 : 140 }}>
            <ActionButton
              variant="contained"
              color="success"
              size="small"
              onClick={() => handleAddGrade(student)}
              disabled={isSubmitting}
            >
              {isMobile ? '+' : 'Add Grade'}
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
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">Attendance</Typography>
                  <StatusBadge status={getAttendanceStatus(student.attendance_percentage)}>
                    {student.attendance_percentage.toFixed(1)}%
                  </StatusBadge>
                  <Typography variant="body2">
                    Days: {student.attendance_days}
                  </Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">AI Insights</Typography>
                  <AIInsightsBox insights={student.ai_insights} />
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
};

export default StudentTableRow;
