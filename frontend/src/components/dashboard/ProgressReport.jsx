import React from 'react';
import { Button, Box } from '@mui/material';
import { useNotification } from '../../contexts/NotificationContext';
import {
  ProgressReportSection,
  ReportDates,
  DateLabel,
  DateValue
} from './StyledComponents';

const ProgressReport = () => {
  const { showNotification } = useNotification();

  const handleGenerateReport = () => {
    showNotification('Progress report generation feature coming soon!');
  };

  const handleDateClick = () => {
    showNotification('Progress report history feature coming soon!');
  };

  return (
    <ProgressReportSection>
      <ReportDates>
        <Box>
          <DateLabel>Last Progress Report:</DateLabel>
          <DateValue component="a" href="#" onClick={handleDateClick}>Oct 15, 2024</DateValue>
        </Box>
        <Box>
          <DateLabel>Next Progress Report:</DateLabel>
          <DateValue>Dec 15, 2024</DateValue>
        </Box>
      </ReportDates>
      <Button variant="contained" color="primary" onClick={handleGenerateReport}>
        Generate Progress Report
      </Button>
    </ProgressReportSection>
  );
};

export default ProgressReport;
