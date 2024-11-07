import React, { useState, useRef, useEffect } from 'react';
import { Box } from '@mui/material';

const ResizableColumn = ({ children, onResize, width }) => {
  const [isResizing, setIsResizing] = useState(false);
  const [isHovering, setIsHovering] = useState(false);
  const [resizePreview, setResizePreview] = useState(null);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const columnRef = useRef(null);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return;
      
      const diff = e.pageX - startX.current;
      const newWidth = Math.max(100, startWidth.current + diff);
      
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
          alignItems: 'center',
          '&::after': {
            content: '""',
            position: 'absolute',
            right: 0,
            top: 0,
            bottom: 0,
            width: '1px',
            backgroundColor: '#e0e0e0',
          }
        }}
      >
        {children}
        <Box
          onMouseEnter={() => setIsHovering(true)}
          onMouseLeave={() => setIsHovering(false)}
          sx={{
            position: 'absolute',
            right: -8,
            top: 0,
            bottom: 0,
            width: '16px',
            cursor: 'col-resize',
            zIndex: 2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: isHovering || isResizing ? 'rgba(126, 58, 242, 0.1)' : 'transparent',
            transition: 'background-color 0.2s',
            '&::after': {
              content: '""',
              position: 'absolute',
              right: '7px',
              width: '2px',
              height: '100%',
              backgroundColor: isHovering || isResizing ? '#7e3af2' : '#e0e0e0',
              transition: 'background-color 0.2s',
            },
            '&::before': {
              content: '""',
              position: 'absolute',
              right: '7px',
              width: '2px',
              height: '100%',
              backgroundColor: isHovering || isResizing ? '#7e3af2' : '#e0e0e0',
              opacity: isHovering || isResizing ? 1 : 0,
              transform: 'translateX(-3px)',
              transition: 'opacity 0.2s, background-color 0.2s',
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
            width: '2px',
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
