import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ScoreCell } from '../pages/Gradebook';

const setup = (props = {}) => {
  const onSave = vi.fn(() => Promise.resolve());
  render(<ScoreCell label="Ada, Quiz 1" max={10} value={7} onSave={onSave} cell="0:0" {...props} />);
  return { onSave, input: screen.getByLabelText('Ada, Quiz 1'), user: userEvent.setup() };
};

describe('ScoreCell', () => {
  it('saves once on blur when the value changed', async () => {
    const { onSave, input, user } = setup();
    await user.clear(input); await user.type(input, '9'); await user.tab();
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith(9);
  });

  it('does not save when nothing changed', async () => {
    const { onSave, input, user } = setup();
    await user.click(input); await user.tab();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('saves null when cleared (missing)', async () => {
    const { onSave, input, user } = setup();
    await user.clear(input); await user.tab();
    expect(onSave).toHaveBeenCalledWith(null);
  });

  it('flags invalid input and reverts without saving', async () => {
    const { onSave, input, user } = setup();
    await user.clear(input); await user.type(input, 'abc');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/enter a number/i)).toBeInTheDocument();
    await user.tab();
    expect(onSave).not.toHaveBeenCalled();
    expect(input).toHaveValue('7');
  });

  it('warns above max points but still allows saving', async () => {
    const { onSave, input, user } = setup();
    await user.clear(input); await user.type(input, '12');
    expect(screen.getByText('Over 10')).toBeInTheDocument();
    await user.tab();
    expect(onSave).toHaveBeenCalledWith(12);
  });

  it('reverts the draft when the save fails', async () => {
    const { input, user } = setup({ onSave: vi.fn(() => Promise.reject(new Error('boom'))) });
    await user.clear(input); await user.type(input, '3'); await user.tab();
    await vi.waitFor(() => expect(input).toHaveValue('7'));
  });

  it('Escape undoes the edit', async () => {
    const { onSave, input, user } = setup();
    await user.clear(input); await user.type(input, '4'); await user.keyboard('{Escape}');
    expect(input).toHaveValue('7');
    await user.tab();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('Enter moves down a column via onNav, else commits by blurring', async () => {
    const onNav = vi.fn(() => true);
    const { input, user } = setup({ onNav });
    await user.click(input); await user.keyboard('{Enter}');
    expect(onNav).toHaveBeenCalledWith('down', '0:0');
    onNav.mockReturnValue(false);
    await user.keyboard('{Enter}');
    expect(input).not.toHaveFocus();
  });
});
