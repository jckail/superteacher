import { styled } from '@mui/material';
import { TableContainer, TableHead, TableCell, Box } from '@mui/material';

export const StyledTableContainer = styled(TableContainer)({
  position: 'relative',
  height: '100%',
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
    padding: 0, // Remove default padding to allow ResizableColumn to control spacing
  }
});

export const StyledTableCell = styled(TableCell)(({ theme, width }) => ({
  backgroundColor: '#f3f0ff',
  padding: 0, // Remove default padding to allow ResizableColumn to control spacing
  fontWeight: 500,
  color: '#374151',
  borderBottom: '1px solid #e9ecef',
  width: width,
  minWidth: width,
  maxWidth: width,
  position: 'relative', // Needed for proper resize handle positioning
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
      right: '24px', // Adjusted to not overlap with resize handle
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

export const ActionButton = styled('button')(({ theme }) => ({
  width: '100%',
  marginBottom: '8px',
  textTransform: 'none',
  padding: '6px 12px',
  fontSize: '0.875rem',
  fontWeight: 500,
  borderRadius: '4px',
  border: 'none',
  cursor: 'pointer',
  color: 'white',
  transition: 'background-color 0.2s',
  '&.MuiButton-containedPrimary': {
    backgroundColor: '#7e3af2',
    '&:hover': {
      backgroundColor: '#6c2bd9',
    },
  },
  '&.MuiButton-containedError': {
    backgroundColor: '#e02424',
    '&:hover': {
      backgroundColor: '#c81e1e',
    },
  },
  '&.MuiButton-containedSuccess': {
    backgroundColor: '#0e9f6e',
    '&:hover': {
      backgroundColor: '#057a55',
    },
  },
  '&.MuiButton-containedWarning': {
    backgroundColor: '#ff5a1f',
    '&:hover': {
      backgroundColor: '#dc4719',
    },
  },
  [theme.breakpoints.down('sm')]: {
    fontSize: '0.75rem',
    padding: '4px 8px',
    marginBottom: '4px',
  }
}));

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
