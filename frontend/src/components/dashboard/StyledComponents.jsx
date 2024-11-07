import { styled } from '@mui/material';
import { Box, Typography } from '@mui/material';

export const ProgressReportSection = styled(Box)(({ theme }) => ({
  padding: '16px 24px',
  background: '#f3f0ff',
  borderBottom: '1px solid #e9ecef',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  position: 'sticky',
  top: 0,
  zIndex: 1100,
  backgroundColor: '#f3f0ff',
}));

export const ReportDates = styled(Box)({
  display: 'flex',
  gap: '24px',
  alignItems: 'center',
});

export const DateLabel = styled(Typography)({
  fontSize: '14px',
  color: '#6b7280',
});

export const DateValue = styled(Typography)({
  color: '#7e3af2',
  fontWeight: 500,
  cursor: 'pointer',
});

export const Controls = styled(Box)(({ theme }) => ({
  padding: '16px 24px',
  display: 'flex',
  gap: '12px',
  alignItems: 'center',
  borderBottom: '1px solid #e9ecef',
  position: 'sticky',
  top: '72px',
  zIndex: 1100,
  backgroundColor: '#fff',
}));

export const TableContainer = styled(Box)({
  height: 'calc(100vh - 144px)', // Subtract height of fixed sections
  overflow: 'auto',
});
