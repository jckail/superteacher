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
  [theme.breakpoints.down('sm')]: {
    padding: '8px 12px',
    flexDirection: 'column',
    gap: '8px',
    '& .MuiButton-root': {
      fontSize: '0.7rem',
      padding: '4px 8px',
      width: '100%'
    }
  }
}));

export const ReportDates = styled(Box)(({ theme }) => ({
  display: 'flex',
  gap: '24px',
  alignItems: 'center',
  [theme.breakpoints.down('sm')]: {
    gap: '12px',
    width: '100%',
    justifyContent: 'space-between'
  }
}));

export const DateLabel = styled(Typography)(({ theme }) => ({
  fontSize: '14px',
  color: '#6b7280',
  [theme.breakpoints.down('sm')]: {
    fontSize: '12px'
  }
}));

export const DateValue = styled(Typography)(({ theme }) => ({
  color: '#7e3af2',
  fontWeight: 500,
  cursor: 'pointer',
  [theme.breakpoints.down('sm')]: {
    fontSize: '12px'
  }
}));

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
  [theme.breakpoints.down('sm')]: {
    padding: '8px 12px',
    flexWrap: 'wrap',
    gap: '8px',
    '& .MuiButton-root': {
      fontSize: '0.7rem',
      padding: '4px 8px',
      flex: '1 1 auto',
      minWidth: 'auto'
    },
    '& .MuiTextField-root': {
      flex: '1 1 100%'
    }
  }
}));

export const TableContainer = styled(Box)({
  height: 'calc(100vh - 144px)', // Subtract height of fixed sections
  overflow: 'auto',
});
