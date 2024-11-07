import React, { useState } from 'react';
import {
  Table,
  TableBody,
  TableRow,
  Box,
  useTheme,
  useMediaQuery,
} from '@mui/material';
import { useNotification } from '../../contexts/NotificationContext';
import config from '../../config';

import { StyledTableContainer, StyledTableHead, StyledTableCell } from './StyledComponents';
import HeaderCell from './HeaderCell';
import StudentTableRow from './StudentTableRow';
import AddGradeDialog from './AddGradeDialog';

const initialColumnWidths = {
  class_id: 120,
  section: 120,
  id: 120,
  name: 200,
  performance: 150,
  tests: 200,
  homework: 200,
  attendance: 150,
  insights: 300,
  actions: 150
};

const initialGradeState = {
  testName: '',
  score: '',
  totalPoints: '',
  date: new Date().toISOString().split('T')[0],
  gradeType: 'test'
};

const columnConfig = [
  { key: 'class_id', label: 'Class ID', mobileHide: true },
  { key: 'section', label: 'Section', mobileHide: true },
  { key: 'id', label: 'Student ID' },
  { key: 'name', label: 'Name' },
  { key: 'performance', label: 'Performance', sortKey: 'gpa' },
  { key: 'tests', label: 'Tests', showSort: false, mobileHide: true },
  { key: 'homework', label: 'Homework', showSort: false, mobileHide: true },
  { key: 'attendance', label: 'Attendance', sortKey: 'attendance_percentage', mobileHide: true },
  { key: 'insights', label: 'AI Insights', showSort: false, mobileHide: true },
  { key: 'actions', label: 'Actions', showSort: false }
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
    setColumnWidths(prev => ({
      ...prev,
      [column]: newWidth
    }));
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
        <Table stickyHeader>
          <StyledTableHead>
            <TableRow>
              {columnConfig.map(({ key, label, sortKey, showSort = true, mobileHide }) => (
                (!mobileHide || !isMobile) && (
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
                )
              ))}
              {isMobile && (
                <StyledTableCell>Details</StyledTableCell>
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
