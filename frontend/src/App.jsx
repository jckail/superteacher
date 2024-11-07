import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Header from './components/Header';
import Dashboard from './pages/Dashboard';
import Footer from './components/Footer';
import NotificationBanner from './components/NotificationBanner';
import { NotificationProvider, useNotification } from './contexts/NotificationContext';

const theme = createTheme({
  palette: {
    primary: {
      main: '#7e3af2',
    },
    background: {
      default: '#f8f7ff',
    },
  },
  typography: {
    fontFamily: 'Inter, sans-serif',
  },
});

const AppContent = () => {
  const { notification, hideNotification } = useNotification();

  return (
    <Router>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Header />
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
        <Footer />
        <NotificationBanner
          open={notification.open}
          message={notification.message}
          onClose={hideNotification}
        />
      </div>
    </Router>
  );
};

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <NotificationProvider>
        <AppContent />
      </NotificationProvider>
    </ThemeProvider>
  );
}

export default App;
