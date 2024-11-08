import React from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Box,
  IconButton,
  Avatar,
  styled,
} from '@mui/material';
import NotificationsIcon from '@mui/icons-material/Notifications';
import PersonIcon from '@mui/icons-material/Person';
import { useNotification } from '../contexts/NotificationContext';

const BrandLogo = styled(Box)(({ theme }) => ({
  background: theme.palette.primary.main,
  color: 'white',
  width: 32,
  height: 32,
  borderRadius: 8,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 600,
  marginRight: theme.spacing(1.5),
}));

const Header = () => {
  const { showNotification } = useNotification();

  const handleNotificationsClick = () => {
    showNotification('Notifications feature coming soon!');
  };

  const handleProfileClick = () => {
    showNotification('Profile management coming soon!');
  };

  return (
    <AppBar position="static" color="default" elevation={1}>
      <Toolbar>
        <Box display="flex" alignItems="center" flexGrow={1}>
          <BrandLogo>
            <Typography variant="subtitle1">🦸‍♀️</Typography>
          </BrandLogo>
          <Typography variant="h6" component="div">
          SuperTeacher
          </Typography>
        </Box>

        <Box display="flex" alignItems="center" gap={2}>
          <IconButton color="inherit" onClick={handleNotificationsClick}>
            <NotificationsIcon />
          </IconButton>
          <IconButton color="inherit" onClick={handleProfileClick}>
            <PersonIcon />
          </IconButton>
          <Box display="flex" alignItems="center" gap={1}>
            <Avatar sx={{ bgcolor: 'primary.light', color: 'primary.main' }}>
              MS
            </Avatar>
            <Typography variant="subtitle1">Mr. Smith</Typography>
          </Box>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
