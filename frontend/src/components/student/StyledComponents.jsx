import { styled } from '@mui/material';
import { TableContainer, TableHead, TableCell, Box, Button } from '@mui/material';

export const StyledTableContainer = styled(TableContainer)({
  position: 'relative',
  height: '100%',
  overflowX: 'auto',
  '& table': {
    borderCollapse: 'separate',
    borderSpacing: 0,
  }
});

export const StyledTableHead = styled(TableHead)({
  position: 'sticky',
  top: 0,
  zIndex: 1000,
  backgroundColor: '#f3f0ff',
  '& th': {
    borderBottom: '2px solid #e9ecef',
    padding: 0,
  }
});

export const StyledTableCell = styled(TableCell)(({ theme, width }) => ({
  backgroundColor: '#f3f0ff',
  padding: 0,
  fontWeight: 500,
  color: '#374151',
  borderBottom: '1px solid #e9ecef',
  width: width,
  minWidth: width,
  maxWidth: width,
  position: 'relative',
  '& .sortable': {
    cursor: 'pointer',
    position: 'relative',
    width: '100%',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    
    '&::after': {
      content: '"↕"',
      position: 'absolute',
      right: '24px',
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
    fontSize: '0.875rem',
  }
}));

export const HeaderContent = styled(Box)({
  padding: '12px 16px',
  width: '100%',
  height: '100%',
  display: 'flex',
  alignItems: 'center',
});

export const StatusBadge = styled('div')(({ theme, status }) => ({
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

export const ActionButton = styled(Button)({
  width: '100%',
  marginBottom: '8px',
  textTransform: 'none',
  padding: '6px 12px',
  fontSize: '0.875rem',
  fontWeight: 500,
  borderRadius: '4px',
  color: 'white',
  '&.MuiButton-containedSuccess': {
    backgroundColor: '#22c55e',
    '&:hover': {
      backgroundColor: '#16a34a',
    },
  },
  '&.MuiButton-containedWarning': {
    backgroundColor: '#eab308',
    '&:hover': {
      backgroundColor: '#ca8a04',
    },
  },
  '&.MuiButton-containedInfo': {
    backgroundColor: '#0ea5e9',
    '&:hover': {
      backgroundColor: '#0284c7',
    },
  },
  '&.MuiButton-containedError': {
    backgroundColor: '#ef4444',
    '&:hover': {
      backgroundColor: '#dc2626',
    },
  },
});

export const ScoreCard = styled('div')(({ theme }) => ({
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
