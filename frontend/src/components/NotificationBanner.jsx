import React from 'react';
import { Snackbar, Alert } from '@mui/material';

const NotificationBanner = ({ open, message, onClose }) => {
  return (
    <Snackbar
      open={open}
      autoHideDuration={3000}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    >
      <Alert 
        onClose={onClose} 
        severity="error" 
        sx={{ 
          width: '100%',
          backgroundColor: '#ff1744',
          color: 'white',
          '& .MuiAlert-icon': {
            color: 'white'
          }
        }}
      >
        {message}
      </Alert>
    </Snackbar>
  );
};

export default NotificationBanner;
