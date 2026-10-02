import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api';
import EmailLogin from '../pages/EmailLogin';
import Login from '../pages/Login';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: request }));
beforeEach(() => { request.mockReset(); });

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise((success, failure) => { resolve = success; reject = failure; });
  return { promise, resolve, reject };
}
const cases = [
  { mode: 'passcode', label: 'Passcode', value: 'synthetic-passcode', button: 'Sign in',
    failure: new ApiError(401, 'Unauthorized'), message: 'Incorrect passcode.' },
  { mode: 'email', label: 'Email address', value: 'synthetic@example.test', button: 'Email me a sign-in link',
    failure: new ApiError(429, 'Rate limited'), message: 'Too many requests from this network. Please wait a few minutes and try again.' },
] as const;

for (const scenario of cases) {
  describe(`${scenario.mode} sign-in accessibility`, () => {
    it('associates failure feedback with the field and clears it on retry', async () => {
      const first = deferred();
      const second = deferred();
      request.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
      const user = userEvent.setup();
      const success = vi.fn();
      render(scenario.mode === 'passcode' ? <Login onSuccess={success} /> : <EmailLogin />);
      const field = screen.getByLabelText(scenario.label);
      expect(field).not.toHaveAccessibleDescription();
      await user.type(field, scenario.value);
      await user.click(screen.getByRole('button', { name: scenario.button }));
      await act(async () => first.reject(scenario.failure));
      expect(screen.getByRole('alert')).toHaveTextContent(scenario.message);
      expect(field).toHaveAccessibleDescription(scenario.message);
      await user.click(screen.getByRole('button', { name: scenario.button }));
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(field).not.toHaveAccessibleDescription();
      await act(async () => second.resolve({}));
      expect(request).toHaveBeenCalledTimes(2);
      if (scenario.mode === 'passcode') expect(success).toHaveBeenCalledOnce();
      else expect(screen.getByRole('heading', { name: 'Check your email' })).toHaveFocus();
    });
    it('exposes the pending form state until failure restores retry', async () => {
      const pending = deferred();
      request.mockReturnValue(pending.promise);
      const user = userEvent.setup();
      render(scenario.mode === 'passcode' ? <Login onSuccess={vi.fn()} /> : <EmailLogin />);
      const button = screen.getByRole('button', { name: scenario.button });
      const form = button.closest('form');
      expect(form).toHaveAttribute('aria-busy', 'false');
      await user.type(screen.getByLabelText(scenario.label), scenario.value);
      await user.click(button);
      expect(form).toHaveAttribute('aria-busy', 'true');
      expect(button).toBeDisabled();
      await act(async () => pending.reject(new Error('Connection interrupted')));
      expect(form).toHaveAttribute('aria-busy', 'false');
      expect(button).toBeEnabled();
      expect(screen.getByLabelText(scenario.label)).toHaveAccessibleDescription('Connection interrupted');
    });
  });
}
