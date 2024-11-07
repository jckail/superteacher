import React from 'react';
import { Button, TextField } from '@mui/material';
import { Controls } from './StyledComponents';

const SearchControls = ({
  searchQuery,
  onSearchChange,
  onSearch,
  onAddStudent,
  onAddSection
}) => {
  return (
    <Controls>
      <TextField
        placeholder="Search students, classes, or tests..."
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        sx={{ flex: 1, maxWidth: '400px' }}
      />
      <Button variant="contained" color="primary" onClick={onSearch}>
        Search
      </Button>
      <Button
        variant="contained"
        color="primary"
        onClick={onAddStudent}
      >
        Add New Student
      </Button>
      <Button
        variant="contained"
        color="primary"
        onClick={onAddSection}
      >
        Add New Section
      </Button>
    </Controls>
  );
};

export default SearchControls;
