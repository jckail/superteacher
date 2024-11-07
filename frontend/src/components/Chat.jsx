import React, { useState, useRef, useEffect } from 'react';
import { 
  Fab, 
  Dialog, 
  DialogContent, 
  DialogTitle,
  IconButton,
  Box,
  Typography,
  TextField,
  Button,
  Paper,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SendIcon from '@mui/icons-material/Send';

const Chat = () => {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([
    { type: 'agent', text: 'Hello! I\'m your academic assistant. I can help you with:' },
    { type: 'agent', text: '• Understanding student performance\n• Tracking academic progress\n• Generating insights about your class' }
  ]);
  
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleClickOpen = () => {
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleSendMessage = () => {
    if (message.trim()) {
      // Add user message
      setMessages(prev => [...prev, { type: 'user', text: message }]);
      
      // Simulate agent response
      setTimeout(() => {
        setMessages(prev => [...prev, { 
          type: 'agent', 
          text: 'I understand you\'re asking about ' + message.toLowerCase() + '. Let me help you analyze that based on the available student data.'
        }]);
      }, 1000);
      
      setMessage('');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <>
      <Box
        sx={{
          position: 'fixed',
          bottom: 20,
          left: 20,
          zIndex: 1000,
        }}
      >
        <Fab
          sx={{
            bgcolor: '#7e3af2',
            color: 'white',
            boxShadow: 3,
            '&:hover': {
              bgcolor: '#6c2bd9',
              transform: 'scale(1.05)',
              transition: 'transform 0.2s',
            },
            fontSize: '1.5rem',
          }}
          aria-label="academic support"
          onClick={handleClickOpen}
        >
          🎓
        </Fab>
      </Box>

      <Dialog
        open={open}
        onClose={handleClose}
        maxWidth="sm"
        PaperProps={{
          sx: {
            position: 'fixed',
            bottom: 80,
            left: 20,
            m: 0,
            width: 350,
            borderRadius: 2,
            maxHeight: '70vh',
          }
        }}
      >
        <DialogTitle 
          sx={{ 
            m: 0, 
            p: 2, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            bgcolor: '#7e3af2',
            color: 'white'
          }}
        >
          <div style={{ 
            fontSize: '1.25rem',
            fontWeight: 500,
            fontFamily: '"Roboto","Helvetica","Arial",sans-serif'
          }}>
            Academic Support
          </div>
          <IconButton
            aria-label="close"
            onClick={handleClose}
            sx={{
              color: 'white',
              '&:hover': {
                bgcolor: 'rgba(255,255,255,0.1)',
              }
            }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent 
          sx={{ 
            p: 2,
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            height: '450px'
          }}
        >
          {/* Messages Container */}
          <Box 
            sx={{ 
              flexGrow: 1,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 1,
              mb: 2
            }}
          >
            {messages.map((msg, index) => (
              <Box
                key={index}
                sx={{
                  display: 'flex',
                  justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <Paper
                  elevation={1}
                  sx={{
                    p: 1.5,
                    maxWidth: '85%',
                    backgroundColor: msg.type === 'user' ? '#7e3af2' : '#f3f4f6',
                    color: msg.type === 'user' ? 'white' : 'text.primary',
                    borderRadius: msg.type === 'user' ? '15px 15px 5px 15px' : '15px 15px 15px 5px',
                    whiteSpace: 'pre-line',
                  }}
                >
                  <Typography variant="body1">{msg.text}</Typography>
                </Paper>
              </Box>
            ))}
            <div ref={messagesEndRef} />
          </Box>

          {/* Message Input */}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
            <TextField
              fullWidth
              multiline
              maxRows={4}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask about student performance..."
              variant="outlined"
              size="small"
              sx={{
                '& .MuiOutlinedInput-root': {
                  '&.Mui-focused fieldset': {
                    borderColor: '#7e3af2',
                  },
                },
              }}
            />
            <Button
              variant="contained"
              onClick={handleSendMessage}
              disabled={!message.trim()}
              sx={{ 
                minWidth: 'auto', 
                p: 1,
                bgcolor: '#7e3af2',
                '&:hover': {
                  bgcolor: '#6c2bd9',
                },
              }}
            >
              <SendIcon />
            </Button>
          </Box>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default Chat;
