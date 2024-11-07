import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';

const AddStudentDialog = ({
  open,
  onClose,
  classes,
  sections,
  newStudent,
  onInputChange,
  onSubmit
}) => {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Add New Student</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          name="name"
          label="Name"
          type="text"
          fullWidth
          value={newStudent.name}
          onChange={(e) => onInputChange(e, 'student')}
        />
        <TextField
          margin="dense"
          name="grade"
          label="Grade"
          type="number"
          fullWidth
          value={newStudent.grade}
          onChange={(e) => onInputChange(e, 'student')}
        />
        <FormControl fullWidth margin="dense">
          <InputLabel>Class</InputLabel>
          <Select
            name="class_id"
            value={newStudent.class_id}
            onChange={(e) => onInputChange(e, 'student')}
          >
            {classes.map((cls) => (
              <MenuItem key={cls.id} value={cls.id}>
                {cls.name} ({cls.id})
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl fullWidth margin="dense">
          <InputLabel>Section</InputLabel>
          <Select
            name="section"
            value={newStudent.section}
            onChange={(e) => onInputChange(e, 'student')}
            disabled={!newStudent.class_id}
          >
            {newStudent.class_id && sections[newStudent.class_id]?.map((section) => (
              <MenuItem key={section.name} value={section.name}>
                {section.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Cancel
        </Button>
        <Button 
          onClick={onSubmit} 
          color="primary"
          disabled={!newStudent.name || !newStudent.grade || !newStudent.class_id || !newStudent.section}
        >
          Add
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AddStudentDialog;
