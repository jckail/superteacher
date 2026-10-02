import { test as setup, expect } from '@playwright/test';
import { PASSCODE } from '../playwright.config';

setup('sign in (empty server)', async ({ request }) => {
  const res = await request.post('/api/auth/login', { data: { password: PASSCODE }, headers: { 'X-Requested-With': 'superteacher' } });
  expect(res.ok()).toBeTruthy();
  await request.storageState({ path: '.auth/main.json' });
});
