import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Modal } from '../components/ui';

function Host({ onClose = () => {} }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && (
        <Modal title="Add student" onClose={() => { onClose(); setOpen(false); }}>
          <input aria-label="Name" />
          <button>Save</button>
        </Modal>
      )}
    </>
  );
}

describe('Modal', () => {
  it('is a labelled modal dialog and moves focus inside', async () => {
    const user = userEvent.setup();
    render(<Host />);
    await user.click(screen.getByText('Open'));
    const dlg = screen.getByRole('dialog', { name: 'Add student' });
    expect(dlg).toHaveAttribute('aria-modal', 'true');
    expect(dlg).toContainElement(document.activeElement);
  });

  it('traps Tab and Shift+Tab inside the dialog', async () => {
    const user = userEvent.setup();
    render(<Host />);
    await user.click(screen.getByText('Open'));
    const [name, save] = [screen.getByLabelText('Name'), screen.getByText('Save')];
    expect(name).toHaveFocus();
    await user.tab(); expect(save).toHaveFocus();
    await user.tab(); expect(name).toHaveFocus();          // wrapped, never reaches "Open"
    await user.tab({ shift: true }); expect(save).toHaveFocus();
  });

  it('closes on Escape and restores focus to the opener', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Host onClose={onClose} />);
    const opener = screen.getByText('Open');
    await user.click(opener);
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });
});
