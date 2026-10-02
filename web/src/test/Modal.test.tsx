import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Modal } from '../components/ui';

function Host({ onClose = () => {} }: { onClose?: () => void }) {
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
    expect(dlg).toContainElement(document.activeElement instanceof HTMLElement ? document.activeElement : null);
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

it('does not focus hidden or disabled controls', async () => {
  const user = userEvent.setup();
  render(<Modal title="Hidden fields" onClose={() => {}}><div hidden><button>Hidden</button></div><fieldset disabled><input aria-label="Disabled" /></fieldset><button>Available</button></Modal>);
  expect(screen.getByRole('button', { name: 'Available' })).toHaveFocus();
  await user.tab();
  expect(screen.getByRole('button', { name: 'Available' })).toHaveFocus();
});

it('keeps focus on an empty dialog when tabbing', async () => {
  const user = userEvent.setup();
  render(<Modal title="Empty" onClose={() => {}}>No actions</Modal>);
  const dialog = screen.getByRole('dialog');
  expect(dialog).toHaveFocus();
  await user.tab();
  expect(dialog).toHaveFocus();
});


it('closes only the top dialog when dialogs are nested', async () => {
  const user = userEvent.setup();
  const parentClose = vi.fn();
  function Nested() {
    const [child, setChild] = useState(false);
    return <Modal title="Parent" onClose={parentClose}><button onClick={() => setChild(true)}>Open child</button>{child && <Modal title="Child" onClose={() => setChild(false)}><button>Child action</button></Modal>}</Modal>;
  }
  render(<Nested />);
  const opener = screen.getByRole('button', { name: 'Open child' });
  await user.click(opener);
  expect(screen.getByRole('button', { name: 'Child action' })).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog', { name: 'Child' })).not.toBeInTheDocument();
  expect(parentClose).not.toHaveBeenCalled();
  expect(opener).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(parentClose).toHaveBeenCalledOnce();
});
