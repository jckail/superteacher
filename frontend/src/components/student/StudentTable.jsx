import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableRow,
  Box,
  useTheme,
  useMediaQuery,
  Typography
} from '@mui/material';
import { useNotification } from '../../contexts/NotificationContext';
import config from '../../config';

import { StyledTableContainer, StyledTableHead, StyledTableCell } from './StyledComponents';
import HeaderCell from './HeaderCell';
import StudentTableRow from './StudentTableRow';
import AddGradeDialog from './AddGradeDialog';

const initialColumnWidths = {
  class_id: 80,
  section: 80,
  id: 100,
  name: 150,
  performance: 120,
  tests: 150,
  homework: 150,
  attendance: 100,
  insights: 200,
  actions: 120
};

const initialGradeState = {
  testName: '',
  score: '',
  totalPoints: '',
  date: new Date().toISOString().split('T')[0],
  gradeType: 'test'
};

const columnConfig = [
  { key: 'class_id', label: 'Class ID', desktopOnly: true },
  { key: 'section', label: 'Section', desktopOnly: true },
  { key: 'id', label: 'Student ID', desktopOnly: true },
  { key: 'name', label: 'Name', desktopOnly: true },
  { key: 'class-info', label: 'Class/Section', mobileOnly: true },
  { key: 'student-info', label: 'ID/Name', mobileOnly: true },
  { key: 'performance', label: 'Performance', sortKey: 'gpa' },
  { key: 'tests', label: 'Tests', showSort: false, desktopOnly: true },
  { key: 'homework', label: 'Homework', showSort: false, desktopOnly: true },
  { key: 'attendance', label: 'Attendance', sortKey: 'attendance_percentage', desktopOnly: true },
  { key: 'insights', label: 'AI Insights', showSort: false, desktopOnly: true },
  { key: 'actions', label: 'Actions', showSort: false, desktopOnly: true }
];

function StudentTable({ students, classes, sections, onStudentUpdate }) {
  const { showNotification } = useNotification();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openGradeDialog, setOpenGradeDialog] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [columnWidths, setColumnWidths] = useState(initialColumnWidths);
  const [newGrade, setNewGrade] = useState(initialGradeState);
  
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const handleColumnResize = (column, newWidth) => {
    if (!isMobile) {
      setColumnWidths(prev => ({
        ...prev,
        [column]: newWidth
      }));
    }
  };

  const sortedStudents = React.useMemo(() => {
    if (!sortConfig.key) return students;

    return [...students].sort((a, b) => {
      if (sortConfig.key === 'gpa') {
        return sortConfig.direction === 'asc' 
          ? a.gpa - b.gpa
          : b.gpa - a.gpa;
      }

      if (typeof a[sortConfig.key] === 'string') {
        const aValue = a[sortConfig.key].toLowerCase();
        const bValue = b[sortConfig.key].toLowerCase();
        if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      }

      if (a[sortConfig.key] < b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (a[sortConfig.key] > b[sortConfig.key]) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });
  }, [students, sortConfig]);

  const handleAddGrade = (student) => {
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
      setNewGrade(initialGradeState);
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
        <Table stickyHeader sx={{ width: '100%', maxWidth: '100%' }}>
          <StyledTableHead>
            <TableRow>
              {columnConfig.map(({ key, label, sortKey, showSort = true, desktopOnly, mobileOnly }) => {
                if ((desktopOnly && isMobile) || (mobileOnly && !isMobile)) {
                  return null;
                }
                return (
                  <HeaderCell
                    key={key}
                    columnKey={key}
                    label={label}
                    width={columnWidths[key]}
                    onResize={handleColumnResize}
                    sortConfig={sortConfig}
                    onSort={handleSort}
                    sortKey={sortKey}
                    showSort={showSort}
                  />
                );
              })}
              {isMobile && (
                <StyledTableCell data-column="details" sx={{ width: '12.5%' }} />
              )}
            </TableRow>
          </StyledTableHead>
          <TableBody>
            {sortedStudents.map((student) => (
              <StudentTableRow
                key={student.id}
                student={student}
                handleAddGrade={handleAddGrade}
                handleContactParent={handleContactParent}
                handleAddEvent={handleAddEvent}
                handleEscalate={handleEscalate}
                isSubmitting={isSubmitting}
                columnWidths={columnWidths}
              />
            ))}
          </TableBody>
        </Table>
      </StyledTableContainer>

      <AddGradeDialog
        open={openGradeDialog}
        onClose={() => setOpenGradeDialog(false)}
        student={selectedStudent}
        newGrade={newGrade}
        onGradeChange={setNewGrade}
        onSubmit={handleSubmitGrade}
        isSubmitting={isSubmitting}
      />
    </>
  );
}

export default StudentTable;
