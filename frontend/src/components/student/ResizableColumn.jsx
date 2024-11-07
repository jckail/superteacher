import React, { useState, useRef, useEffect } from 'react';
import { Box } from '@mui/material';

const ResizableColumn = ({ children, onResize, width }) => {
  const [isResizing, setIsResizing] = useState(false);
  const [resizePreview, setResizePreview] = useState(null);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const columnRef = useRef(null);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return;
      
      const diff = e.pageX - startX.current;
      const newWidth = Math.max(100, startWidth.current + diff); // Minimum width of 100px
      
      // Update preview line position
      if (columnRef.current) {
        const columnRect = columnRef.current.getBoundingClientRect();
        setResizePreview(columnRect.left + newWidth);
      }
      
      onResize(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      setResizePreview(null);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, onResize]);

  const startResize = (e) => {
    e.preventDefault();
    setIsResizing(true);
    startX.current = e.pageX;
    startWidth.current = width;

    // Set initial preview line position
    if (columnRef.current) {
      const columnRect = columnRef.current.getBoundingClientRect();
      setResizePreview(columnRect.left + width);
    }
  };

  return (
    <>
      <Box 
        ref={columnRef}
        sx={{ 
          position: 'relative', 
          width: width, 
          height: '100%', 
          display: 'flex', 
          alignItems: 'center'
        }}
      >
        {children}
        <Box
          sx={{
            position: 'absolute',
            right: -4,
            top: 0,
            bottom: 0,
            width: 8,
            cursor: 'col-resize',
            zIndex: 2,
            '&:hover': {
              '&::after': {
                backgroundColor: 'rgba(0, 0, 0, 0.1)',
              }
            },
            '&::after': {
              content: '""',
              position: 'absolute',
              right: 3,
              top: 0,
              bottom: 0,
              width: 2,
              backgroundColor: isResizing ? '#7e3af2' : 'transparent',
              transition: 'background-color 0.2s'
            }
          }}
          onMouseDown={startResize}
        />
      </Box>
      {isResizing && (
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            bottom: 0,
            left: resizePreview,
            width: 2,
            backgroundColor: '#7e3af2',
            zIndex: 9999,
            pointerEvents: 'none'
          }}
        />
      )}
    </>
  );
};

export default ResizableColumn;
