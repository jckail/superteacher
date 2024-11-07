import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  useMediaQuery,
  useTheme,
} from '@mui/material';

const AddGradeDialog = ({
  open,
  onClose,
  student,
  newGrade,
  onGradeChange,
  onSubmit,
  isSubmitting
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    onGradeChange(prev => ({
      ...prev,
      [name]: value
    }));
  };

  return (
    <Dialog 
      open={open} 
      onClose={onClose}
      fullScreen={isMobile}
    >
      <DialogTitle>Add Grade for {student?.name}</DialogTitle>
      <DialogContent>
        <FormControl fullWidth margin="dense">
          <InputLabel>Grade Type</InputLabel>
          <Select
            name="gradeType"
            value={newGrade.gradeType}
            onChange={handleInputChange}
          >
            <MenuItem value="test">Test</MenuItem>
            <MenuItem value="homework">Homework</MenuItem>
          </Select>
        </FormControl>
        <TextField
          autoFocus
          margin="dense"
          name="testName"
          label={newGrade.gradeType === 'test' ? "Test Name" : "Homework Name"}
          type="text"
          fullWidth
          value={newGrade.testName}
          onChange={handleInputChange}
        />
        <TextField
          margin="dense"
          name="score"
          label="Score"
          type="number"
          fullWidth
          value={newGrade.score}
          onChange={handleInputChange}
        />
        <TextField
          margin="dense"
          name="totalPoints"
          label="Total Points"
          type="number"
          fullWidth
          value={newGrade.totalPoints}
          onChange={handleInputChange}
        />
        <TextField
          margin="dense"
          name="date"
          label="Date"
          type="date"
          fullWidth
          value={newGrade.date}
          onChange={handleInputChange}
          InputLabelProps={{
            shrink: true,
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Cancel
        </Button>
        <Button onClick={onSubmit} color="primary" disabled={isSubmitting}>
          Add Grade
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AddGradeDialog;
