import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ScoreCell } from '../pages/Gradebook';

describe('ScoreCell accessible descriptions', () => {
  it('associates an invalid score warning with its own input', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<ScoreCell label="Ada, Quiz" value={7} max={10} onSave={onSave} />);
    const input = screen.getByRole('textbox', { name: 'Ada, Quiz' });
    await user.clear(input); await user.type(input, 'abc');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Enter a number ≥ 0/);
    expect(screen.getByRole('status')).toHaveTextContent('Ada, Quiz');
    expect(onSave).not.toHaveBeenCalled();
  });

  it('describes maximum points and the meaning of a blank score before editing', () => {
    render(<ScoreCell label="Ada, Quiz" value={null} max={10} onSave={vi.fn()} />);
    const input = screen.getByRole('textbox', { name: 'Ada, Quiz' });
    expect(input).toHaveAccessibleDescription(/Score out of 10/);
    expect(input).toHaveAccessibleDescription(/Leave blank for no recorded score/);
  });

  it('associates an extra-credit warning while preserving valid over-maximum saving', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<ScoreCell label="Ada, Quiz" value={7} max={10} onSave={onSave} />);
    const input = screen.getByRole('textbox', { name: 'Ada, Quiz' });
    await user.clear(input); await user.type(input, '12');
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).toHaveAccessibleDescription(/Over 10/);
    expect(input).toHaveAccessibleDescription(/extra credit/);
    await user.tab();
    expect(onSave).toHaveBeenCalledWith(12);
  });

  it('keeps warning descriptions unique when several student cells are mounted', async () => {
    const user = userEvent.setup();
    render(<><ScoreCell label="Ada, Quiz" value={7} max={10} onSave={vi.fn()} /><ScoreCell label="Ben, Quiz" value={8} max={20} onSave={vi.fn()} /></>);
    const ada = screen.getByRole('textbox', { name: 'Ada, Quiz' });
    const ben = screen.getByRole('textbox', { name: 'Ben, Quiz' });
    await user.clear(ada); await user.type(ada, 'abc');
    expect(ada).toHaveAccessibleDescription(/Enter a number ≥ 0/);
    expect(ben).toHaveAccessibleDescription(/Score out of 20/);
    expect(ben).not.toHaveAccessibleDescription(/Enter a number ≥ 0/);
    const ids = Array.from(document.querySelectorAll('[id]'), (element) => element.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('removes obsolete warnings from the input description after Escape restores the score', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<ScoreCell label="Ada, Quiz" value={7} max={10} onSave={onSave} />);
    const input = screen.getByRole('textbox', { name: 'Ada, Quiz' });
    await user.clear(input); await user.type(input, '-1');
    expect(input).toHaveAccessibleDescription(/Enter a number ≥ 0/);
    await user.keyboard('{Escape}');
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).not.toHaveAccessibleDescription(/Enter a number ≥ 0/);
    expect(input).toHaveAccessibleDescription(/Score out of 10/);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(input).toHaveValue('7');
    await user.tab(); expect(onSave).not.toHaveBeenCalled();
  });

  it('explains a blank score without rendering an undefined maximum', () => {
    render(<ScoreCell label="Ada, Quiz" value={null} onSave={vi.fn()} />);
    const input = screen.getByRole('textbox', { name: 'Ada, Quiz' });
    expect(input).toHaveAccessibleDescription(/Leave blank for no recorded score/);
    expect(input).not.toHaveAccessibleDescription(/undefined/);
  });
});
