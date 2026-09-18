import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const login = process.env.ASM_BROWSER_LOGIN;
const passwordFile = process.env.ASM_BROWSER_PASSWORD_FILE;
const password = passwordFile ? readFileSync(passwordFile, 'utf8') : undefined;
if (!login || !password) throw new Error('Private browser credentials are required');
const credentials = { login, password };

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/'); await page.getByLabel('Логин').fill(credentials.login); await page.getByLabel('Пароль').fill(credentials.password); await page.getByRole('button', { name: 'Войти' }).click(); await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
}

test('login, Business read, reload and confirmed logout', async ({ page }) => {
  await signIn(page); await expect(page.getByText('Synthetic browser business')).toBeVisible();
  await page.reload(); await expect(page.getByText('Synthetic browser business')).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click(); await expect(page.getByText(/Выход выполнен/)).toBeVisible();
  await page.reload(); await expect(page.getByLabel('Пароль')).toBeVisible(); await expect(page.getByText('Synthetic browser business')).toHaveCount(0);
});

test('invalid password and tampered workspace never expose protected data', async ({ page }) => {
  await page.goto('/'); await page.getByLabel('Логин').fill(credentials.login); await page.getByLabel('Пароль').fill(`${credentials.password}x`); await page.getByRole('button', { name: 'Войти' }).click(); await expect(page.getByText('Неверный логин или пароль.')).toBeVisible();
  const response = await page.request.get('/api/v1/workspaces/00000000-0000-4000-8000-000000000000/businesses'); expect([401, 403, 404]).toContain(response.status());
});

test('rotation keeps expiry and recovered CSRF completes logout', async ({ page }) => {
  await signIn(page); const before = await page.getByText(/Сессия действует до:/).textContent();
  await page.getByRole('button', { name: 'Обновить защиту сессии' }).click(); await expect(page.getByText(/Защита сессии обновлена/)).toBeVisible(); expect(await page.getByText(/Сессия действует до:/).textContent()).toBe(before);
  await page.getByRole('button', { name: 'Выйти' }).click(); await expect(page.getByText(/Выход выполнен/)).toBeVisible();
});

test('lost rotation response is recovered from the real current session without replay', async ({ page }) => {
  await signIn(page); let rotations = 0;
  await page.route('**/api/v1/auth/rotate', async (route) => { rotations++; await route.fetch(); await route.abort('failed'); });
  await page.getByRole('button', { name: 'Обновить защиту сессии' }).click(); await expect(page.getByText('ACTIVE SESSION')).toBeVisible(); expect(rotations).toBe(1);
});

test('@narrow keyboard navigation, storage and Ops isolation', async ({ page }) => {
  await page.goto('/'); await page.keyboard.press('Tab'); await expect(page.getByRole('link', { name: 'Business Console' })).toBeFocused(); await signIn(page);
  expect(await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage), cookie: document.cookie }))).toEqual({ local: [], session: [], cookie: '' });
  await page.goto('/ops/'); await expect(page.getByRole('heading', { name: 'Platform Operations' })).toBeVisible(); await expect(page.getByText('Synthetic browser business')).toHaveCount(0);
});
