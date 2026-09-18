import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { parseSession } from './api';

const uid = '11111111-1111-4111-8111-111111111111';
const wid = '22222222-2222-4222-8222-222222222222';
const bid = '33333333-3333-4333-8333-333333333333';
const bootstrap = (csrf = 'bootstrap') => ({ csrf_token: csrf, expires_at: '2030-01-01T00:00:00Z' });
const session = (csrf = 'csrf-new') => ({ user_account_id: uid, expires_at: '2030-01-01T00:00:00Z', csrf_token: csrf, memberships: [{ workspace_id: wid, role: 'OWNER', permissions: ['tenancy:read'] }] });
const ok = (body: unknown, status = 200, headers?: HeadersInit) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const fail = (status: number, code: string, headers?: HeadersInit) => ok({ error: { code } }, status, headers);

describe('Business Console auth', () => {
  it('shows loading then anonymous without treating 401 as a crash', async () => {
    let resolve!: (v: Response) => void; vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((r) => { resolve = r; })));
    render(<App pathname="/" />); expect(screen.getByText('Проверяем сессию')).toBeVisible(); resolve(fail(401, 'SESSION_REQUIRED'));
    expect(await screen.findByRole('heading', { name: 'Вход в консоль' })).toBeVisible();
  });
  it('logs in once, clears password, and renders server Business data', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(fail(401, 'SESSION_REQUIRED')).mockResolvedValueOnce(ok(bootstrap())).mockResolvedValueOnce(ok(session())).mockResolvedValueOnce(ok({ businesses: [{ workspace_id: wid, id: bid, name: 'Synthetic business', status: 'ACTIVE', version: 1, created_at: '2030-01-01T00:00:00Z' }] })); vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByLabelText('Логин'); await user.type(screen.getByLabelText('Логин'), 'owner.test'); await user.type(screen.getByLabelText('Пароль'), 'correct-password'); await user.dblClick(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByText('Synthetic business')).toBeVisible(); expect(fetch).toHaveBeenCalledTimes(4); expect(screen.queryByDisplayValue('correct-password')).not.toBeInTheDocument();
    expect(fetch.mock.calls[2][1]).toMatchObject({ credentials: 'include' });
  });
  it('shows a safe invalid-credential error and supports rate limiting', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(fail(401, 'SESSION_REQUIRED')).mockResolvedValueOnce(ok(bootstrap())).mockResolvedValueOnce(fail(401, 'INVALID_CREDENTIALS')));
    const user = userEvent.setup(); render(<App />); await screen.findByLabelText('Логин'); await user.type(screen.getByLabelText('Логин'), 'owner.test'); await user.type(screen.getByLabelText('Пароль'), 'wrong-password-1'); await user.click(screen.getByRole('button', { name: 'Войти' })); expect(await screen.findByText('Неверный логин или пароль.')).toBeVisible();
  });
  it('recovers an ambiguous login through current-session without replay', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(fail(401, 'SESSION_REQUIRED')).mockResolvedValueOnce(ok(bootstrap())).mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(ok(session())).mockResolvedValueOnce(ok({ businesses: [] })); vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByLabelText('Логин'); await user.type(screen.getByLabelText('Логин'), 'owner.test'); await user.type(screen.getByLabelText('Пароль'), 'correct-password'); await user.click(screen.getByRole('button', { name: 'Войти' })); expect(await screen.findByText(/Пользователь/)).toHaveTextContent(uid); expect(fetch).toHaveBeenCalledTimes(5); expect(fetch.mock.calls.filter(([u]) => String(u).endsWith('/auth/login'))).toHaveLength(1);
  });
  it('uses refreshed CSRF after rotation and confirms logout', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok(session('old'))).mockResolvedValueOnce(ok({ businesses: [] })).mockResolvedValueOnce(ok(session('new'))).mockResolvedValueOnce(ok({ businesses: [] })).mockResolvedValueOnce(ok({}, 204)); vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/); await user.click(screen.getByRole('button', { name: 'Обновить защиту сессии' })); await screen.findByText(/Защита сессии обновлена/); await user.click(screen.getByRole('button', { name: 'Выйти' })); expect(await screen.findByText(/Выход выполнен/)).toBeVisible(); const logout = fetch.mock.calls.find(([url]) => String(url).endsWith('/auth/logout')); expect(JSON.stringify(logout?.[1])).toContain('new');
  });
  it('hides protected data when a Business read returns 403', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(ok(session())).mockResolvedValueOnce(fail(403, 'ACCESS_DENIED'))); render(<App />); expect(await screen.findByText('Нет доступа к выбранному Workspace.')).toBeVisible(); expect(screen.queryByText('Synthetic business')).not.toBeInTheDocument();
  });
  it('ignores a late business response after logout', async () => {
    let businessResolve!: (r: Response) => void; const fetch = vi.fn().mockResolvedValueOnce(ok(session())).mockImplementationOnce(() => new Promise<Response>((r) => { businessResolve = r; })).mockResolvedValueOnce(ok({}, 204)); vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/); await user.click(screen.getByRole('button', { name: 'Выйти' })); businessResolve(ok({ businesses: [{ workspace_id: wid, id: bid, name: 'Late secret', status: 'ACTIVE', version: 1, created_at: '2030-01-01T00:00:00Z' }] })); await waitFor(() => expect(screen.queryByText('Late secret')).not.toBeInTheDocument());
  });
  it('rejects malformed session responses and keeps data hidden', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ user_account_id: uid, csrf_token: 'x', expires_at: 'bad', memberships: [] }))); render(<App />); expect(await screen.findByText('Состояние сессии неизвестно')).toBeVisible(); expect(() => parseSession({})).toThrow('INVALID_RESPONSE');
  });
  it('shows an empty-membership state without inventing a Workspace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ ...session(), memberships: [] })));
    render(<App />); expect(await screen.findByText('Нет доступных memberships.')).toBeVisible(); expect(screen.queryByRole('option')).not.toBeInTheDocument();
  });
  it('surfaces Retry-After on 429 without an automatic retry', async () => {
    const fetch = vi.fn().mockResolvedValue(fail(429, 'RATE_LIMITED', { 'Retry-After': '30' })); vi.stubGlobal('fetch', fetch);
    render(<App />); expect(await screen.findByText(/30/)).toBeVisible(); expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('Ops shell', () => {
  it('keeps readiness and contains no tenant data', async () => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ status: 'ok', component: 'database' }))); render(<App pathname="/ops/" />); expect(await screen.findByText('Проверка готовности пройдена')).toBeVisible(); expect(screen.queryByText(uid)).not.toBeInTheDocument(); });
  it('does not accept invalid readiness or offline responses', async () => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ status: 'invented' }))); render(<App pathname="/ops/" />); expect(await screen.findByText('Сервис недоступен или не готов')).toBeVisible(); });
});
