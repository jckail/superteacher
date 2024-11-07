import React from 'react';
import { StyledTableCell, HeaderContent } from './StyledComponents';
import ResizableColumn from './ResizableColumn';

const HeaderCell = ({ 
  columnKey, 
  label, 
  width, 
  onResize, 
  sortConfig, 
  onSort, 
  sortKey = null,
  showSort = true 
}) => {
  const handleSort = () => {
    if (showSort && onSort) {
      onSort(sortKey || columnKey);
    }
  };

  return (
    <StyledTableCell width={width}>
      <ResizableColumn 
        width={width}
        onResize={(newWidth) => onResize(columnKey, newWidth)}
      >
        <HeaderContent
          className={showSort ? `sortable ${sortConfig.key === (sortKey || columnKey) ? `sorted-${sortConfig.direction}` : ''}` : ''}
          onClick={handleSort}
          sx={{ userSelect: 'none' }}
        >
          {label}
        </HeaderContent>
      </ResizableColumn>
    </StyledTableCell>
  );
};

export default HeaderCell;
