import React, { useState, useEffect } from 'react';
import { Box, Container, Link, Typography, useTheme, useMediaQuery } from '@mui/material';
import config from '../config';
import { useNotification } from '../contexts/NotificationContext';

const Footer = () => {
  const [versionInfo, setVersionInfo] = useState({ version: '', git_commit: '' });
  const { showNotification } = useNotification();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

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
        py: isMobile ? 0.5 : 1,
        px: isMobile ? 1 : 2,
        mt: 'auto',
        backgroundColor: 'background.paper',
        borderTop: 1,
        borderColor: 'divider',
        height: isMobile ? '32px' : '40px',
        display: 'flex',
        alignItems: 'center'
      }}
    >
      <Container 
        maxWidth={false}
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          px: isMobile ? 1 : 2
        }}
      >
        <Typography 
          color="text.secondary" 
          variant="body2"
          sx={{ 
            fontSize: isMobile ? '0.7rem' : '0.75rem',
            whiteSpace: 'nowrap'
          }}
        >
          © 2024 EduTrack Pro
        </Typography>
        
        <Box 
          sx={{ 
            display: 'flex',
            gap: isMobile ? 1.5 : 2,
            alignItems: 'center'
          }}
        >
          <Link 
            href="#" 
            color="primary" 
            underline="hover"
            onClick={handleLinkClick('Privacy')}
            sx={{ 
              fontSize: isMobile ? '0.7rem' : '0.75rem',
              whiteSpace: 'nowrap'
            }}
          >
            Privacy
          </Link>
          <Link 
            href="#" 
            color="primary" 
            underline="hover"
            onClick={handleLinkClick('Terms')}
            sx={{ 
              fontSize: isMobile ? '0.7rem' : '0.75rem',
              whiteSpace: 'nowrap'
            }}
          >
            Terms
          </Link>
          <Link 
            href="#" 
            color="primary" 
            underline="hover"
            onClick={handleLinkClick('Support')}
            sx={{ 
              fontSize: isMobile ? '0.7rem' : '0.75rem',
              whiteSpace: 'nowrap'
            }}
          >
            Support
          </Link>
          {!isMobile && (
            <>
              <Link 
                href="#" 
                color="primary" 
                underline="hover"
                onClick={handleLinkClick('Documentation')}
                sx={{ 
                  fontSize: '0.75rem',
                  whiteSpace: 'nowrap'
                }}
              >
                Docs
              </Link>
              <Typography 
                color="text.secondary" 
                variant="caption" 
                sx={{ 
                  fontSize: '0.7rem',
                  whiteSpace: 'nowrap'
                }}
              >
                v{versionInfo.version}
              </Typography>
            </>
          )}
        </Box>
      </Container>
    </Box>
  );
};

export default Footer;
