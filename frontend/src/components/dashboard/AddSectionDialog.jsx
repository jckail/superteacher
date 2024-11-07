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

const AddSectionDialog = ({
  open,
  onClose,
  classes,
  newSection,
  onInputChange,
  onSubmit
}) => {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Add New Section</DialogTitle>
      <DialogContent>
        <FormControl fullWidth margin="dense">
          <InputLabel>Class</InputLabel>
          <Select
            name="class_id"
            value={newSection.class_id}
            onChange={(e) => onInputChange(e, 'section')}
          >
            {classes.map((cls) => (
              <MenuItem key={cls.id} value={cls.id}>
                {cls.name} ({cls.id})
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          autoFocus
          margin="dense"
          name="name"
          label="Section Name"
          type="text"
          fullWidth
          value={newSection.name}
          onChange={(e) => onInputChange(e, 'section')}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Cancel
        </Button>
        <Button 
          onClick={onSubmit} 
          color="primary"
          disabled={!newSection.name || !newSection.class_id}
        >
          Add
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AddSectionDialog;
