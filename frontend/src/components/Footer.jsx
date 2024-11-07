import React, { useState, useEffect } from 'react';
import { Box, Container, Link, Typography } from '@mui/material';
import config from '../config';
import { useNotification } from '../contexts/NotificationContext';

const Footer = () => {
  const [versionInfo, setVersionInfo] = useState({ version: '', git_commit: '' });
  const { showNotification } = useNotification();

  useEffect(() => {
    const fetchVersionInfo = async () => {
      try {
        const response = await fetch(`${config.apiBaseUrl}/version`);
        if (response.ok) {
          const data = await response.json();
          setVersionInfo(data);
        }
      } catch (error) {
        console.error('Failed to fetch version info:', error);
      }
    };

    fetchVersionInfo();
  }, []);

  const handleLinkClick = (feature) => (e) => {
    e.preventDefault();
    showNotification(`${feature} feature coming soon!`);
  };

  return (
    <Box
      component="footer"
      sx={{
        py: 3,
        px: 2,
        mt: 'auto',
        backgroundColor: 'background.paper',
        borderTop: 1,
        borderColor: 'divider',
      }}
    >
      <Container maxWidth="lg">
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <Typography color="text.secondary" variant="body2">
              © 2024 EduTrack Pro. All rights reserved.
            </Typography>
            <Box sx={{ display: 'flex', gap: 3 }}>
              <Link 
                href="#" 
                color="primary" 
                underline="hover"
                onClick={handleLinkClick('Privacy Policy')}
              >
                Privacy Policy
              </Link>
              <Link 
                href="#" 
                color="primary" 
                underline="hover"
                onClick={handleLinkClick('Terms of Service')}
              >
                Terms of Service
              </Link>
              <Link 
                href="#" 
                color="primary" 
                underline="hover"
                onClick={handleLinkClick('Support')}
              >
                Support
              </Link>
              <Link 
                href="#" 
                color="primary" 
                underline="hover"
                onClick={handleLinkClick('Documentation')}
              >
                Documentation
              </Link>
            </Box>
          </Box>
          <Typography color="text.secondary" variant="caption" align="right">
            Version: {versionInfo.version} | Build: {versionInfo.git_commit}
          </Typography>
        </Box>
      </Container>
    </Box>
  );
};

export default Footer;
