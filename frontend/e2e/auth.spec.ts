import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { requireSafeResult, safeDiagnostic, type SafeResult } from './safe-diagnostic';

const login = process.env.ASM_BROWSER_LOGIN;
const passwordFile = process.env.ASM_BROWSER_PASSWORD_FILE;
const password = passwordFile ? readFileSync(passwordFile, 'utf8') : undefined;
if (!login || !password) throw new Error('Private browser credentials are required');
const credentials = { login, password };

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByLabel('Логин').fill(credentials.login);
  await page.getByLabel('Пароль').fill(credentials.password);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText('ACTIVE SESSION')).toBeVisible();
}

test('login, Business read, reload and confirmed logout', async ({ page }) => {
  await signIn(page);
  await expect(page.getByText('Synthetic browser business')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Synthetic browser business')).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page.getByText(/Выход выполнен/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Пароль')).toBeVisible();
  await expect(page.getByText('Synthetic browser business')).toHaveCount(0);
});

test('invalid password and tampered workspace never expose protected data', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Логин').fill(credentials.login);
  await page.getByLabel('Пароль').fill(`${credentials.password}x`);
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page.getByText('Неверный логин или пароль.')).toBeVisible();
  const response = await page.request.get('/api/v1/workspaces/00000000-0000-4000-8000-000000000000/businesses');
  expect([401, 403, 404]).toContain(response.status());
});

test('rotation keeps expiry and recovered CSRF completes logout', async ({ page }) => {
  await signIn(page);
  const before = await page.getByText(/Сессия действует до:/).textContent();
  await page.getByRole('button', { name: 'Обновить защиту сессии' }).click();
  await expect(page.getByText(/Защита сессии обновлена/)).toBeVisible();
  expect(await page.getByText(/Сессия действует до:/).textContent()).toBe(before);
  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page.getByText(/Выход выполнен/)).toBeVisible();
});

test('lost rotation body with delivered cookie is recovered without replay', async ({ page }) => {
  await signIn(page);
  await expect(page.getByText('Synthetic browser business')).toBeVisible();
  const expiryBefore = await page.getByText(/Сессия действует до:/).textContent();

  let rotations = 0;
  const intercepted = deferred<void>();
  const callbackCompleted = deferred<SafeResult<{ status: number }>>();
  const recoveryResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'GET' && url.pathname === '/api/v1/auth/session';
  });
  const protectedReadResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'GET' && /^\/api\/v1\/workspaces\/[^/]+\/businesses$/.test(url.pathname);
  });

  await page.route('**/api/v1/auth/rotate', async (route) => {
    rotations += 1;
    intercepted.resolve();
    const fetched = await safeDiagnostic('ROTATE_ROUTE_FETCH_FAILED', () => route.fetch());
    if (!fetched.ok) {
      await safeDiagnostic('ROTATE_ROUTE_ABORT_AFTER_FETCH_FAILURE', () => route.abort('failed'));
      callbackCompleted.resolve(fetched);
      return;
    }
    const status = fetched.value.status();
    const aborted = await safeDiagnostic('ROTATE_ROUTE_ABORT_FAILED', () => route.abort('failed'));
    callbackCompleted.resolve(aborted.ok ? { ok: true, value: { status } } : aborted);
  });

  await page.getByRole('button', { name: 'Обновить защиту сессии' }).click();
  await intercepted.promise;
  await expect(page.getByRole('button', { name: 'Обновить защиту сессии' })).toBeDisabled();
  const callback = requireSafeResult(await callbackCompleted.promise);
  expect(callback.status).toBe(200);
  const recovered = await recoveryResponse;
  expect(recovered.status()).toBe(200);
  const protectedRead = await protectedReadResponse;
  expect(protectedRead.status()).toBe(200);

  await expect(page.getByRole('button', { name: 'Обновить защиту сессии' })).toBeEnabled();
  await expect(page.getByText('Synthetic browser business')).toBeVisible();
  expect(await page.getByText(/Сессия действует до:/).textContent()).toBe(expiryBefore);
  expect(rotations).toBe(1);

  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page.getByText(/Выход выполнен/)).toBeVisible();
  expect(rotations).toBe(1);
  await page.unrouteAll({ behavior: 'wait' });
});

test('@narrow keyboard navigation, storage and Ops isolation', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Вход в консоль' })).toBeVisible();
  await expect(page.getByLabel('Логин')).toBeVisible();
  await expect(page.getByLabel('Пароль')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Business Console' })).toBeVisible();
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Business Console' })).toBeFocused();
  await signIn(page);
  expect(await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage), cookie: document.cookie }))).toEqual({ local: [], session: [], cookie: '' });
  await page.goto('/ops/');
  await expect(page.getByRole('heading', { name: 'Platform Operations' })).toBeVisible();
  await expect(page.getByText('Synthetic browser business')).toHaveCount(0);
});
