import React from 'react';
import { Box, Container, Link, Typography } from '@mui/material';

const Footer = () => {
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
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Typography color="text.secondary" variant="body2">
            © 2024 EduTrack Pro. All rights reserved.
          </Typography>
          <Box sx={{ display: 'flex', gap: 3 }}>
            <Link href="#" color="primary" underline="hover">
              Privacy Policy
            </Link>
            <Link href="#" color="primary" underline="hover">
              Terms of Service
            </Link>
            <Link href="#" color="primary" underline="hover">
              Support
            </Link>
            <Link href="#" color="primary" underline="hover">
              Documentation
            </Link>
          </Box>
        </Box>
      </Container>
    </Box>
  );
};

export default Footer;
