import React from 'react';
import { Box, Typography, Tooltip } from '@mui/material';
import { StatusBadge } from './StyledComponents';

const getStatusIcon = (status) => {
  switch (status.toLowerCase()) {
    case 'outstanding':
    case 'excellent':
      return '🌟';
    case 'very good':
    case 'good':
      return '✨';
    case 'fair':
      return '⚠️';
    case 'needs improvement':
    case 'at risk':
      return '❗';
    default:
      return '📊';
  }
};

const AIInsightsBox = ({ insights }) => (
  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
    <StatusBadge 
      status={insights.status.toLowerCase().includes('outstanding') || 
             insights.status.toLowerCase().includes('excellent') ? 'good' : 
             insights.status.toLowerCase().includes('good') ? 'warning' : 'danger'}
    >
      {getStatusIcon(insights.status)} {insights.status}
    </StatusBadge>
    
    {insights.performance_breakdown && (
      <Box sx={{ 
        bgcolor: '#f8fafc', 
        p: 1, 
        borderRadius: '4px',
        display: 'flex',
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 2,
        alignItems: 'center'
      }}>
        <Box sx={{ 
          display: 'flex', 
          gap: 2, 
          flexWrap: 'wrap',
          alignItems: 'center',
          width: '100%'
        }}>
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            Performance:
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
            Academic: {insights.performance_breakdown.academic_strength}
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
            Attendance: {insights.performance_breakdown.attendance_impact}
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
            Homework: {insights.performance_breakdown.homework_consistency}
          </Typography>
        </Box>
      </Box>
    )}
    
    <Tooltip title={insights.recommendation} arrow>
      <Typography 
        variant="body2" 
        color="textSecondary"
        sx={{
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          cursor: 'pointer'
        }}
      >
        {insights.recommendation}
      </Typography>
    </Tooltip>
  </Box>
);

export default AIInsightsBox;
