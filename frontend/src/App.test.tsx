import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { api, parseSession } from './api';

// Preserve the exact M1.2 request/assertion suite; M1.3 integration is covered separately.
vi.mock('./BillingPanel', () => ({ BillingPanel: () => null }));
// Keep the accepted auth request assertions; full messaging integration has its own suite.
const messagingIntegration=vi.hoisted(()=>({enabled:false}));
vi.mock('./MessagingPanel', async importOriginal => {const actual=await importOriginal<typeof import('./MessagingPanel')>();return {MessagingPanel:(props:Parameters<typeof actual.MessagingPanel>[0])=>messagingIntegration.enabled?<actual.MessagingPanel {...props}/>:null};});
// Auth request ordering stays exact; the new owner's boundary is tested in its suite.
vi.mock('./EscalationsPanel', () => ({ EscalationsPanel: () => null }));

const uid = '11111111-1111-4111-8111-111111111111';
const wid = '22222222-2222-4222-8222-222222222222';
const bid = '33333333-3333-4333-8333-333333333333';
const bootstrap = (csrf = 'bootstrap') => ({ csrf_token: csrf, expires_at: '2030-01-01T00:00:00Z' });
const session = (csrf = 'csrf-new') => ({ user_account_id: uid, expires_at: '2030-01-01T00:00:00Z', csrf_token: csrf, memberships: [{ workspace_id: wid, role: 'OWNER', permissions: ['tenancy:read'] }] });
const ok = (body: unknown, status = 200, headers?: HeadersInit) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const fail = (status: number, code: string, headers?: HeadersInit) => ok({ error: { code } }, status, headers);
const deferred = <T,>() => { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

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
  it('preserves logout intent across two ambiguities and uses the latest recheck CSRF once', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(ok(session('initial')))
      .mockResolvedValueOnce(ok({ businesses: [{ workspace_id: wid, id: bid, name: 'Protected business', status: 'ACTIVE', version: 1, created_at: '2030-01-01T00:00:00Z' }] }))
      .mockRejectedValueOnce(new TypeError('logout response lost'))
      .mockResolvedValueOnce(ok(session('recovered-two')))
      .mockRejectedValueOnce(new TypeError('second logout response lost'))
      .mockResolvedValueOnce(ok(session('recovered-three')))
      .mockResolvedValueOnce(ok(null, 204));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText('Protected business');

    await user.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(await screen.findByText('Состояние сессии неизвестно')).toBeVisible();
    expect(screen.queryByText('ACTIVE SESSION')).not.toBeInTheDocument();
    expect(screen.queryByText('Protected business')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Проверить снова' }));

    expect(await screen.findByText(/Выход выполнен/)).toBeVisible();
    const logoutCalls = fetch.mock.calls.filter(([url]) => String(url).endsWith('/auth/logout'));
    expect(logoutCalls).toHaveLength(3);
    expect(logoutCalls.map(([, init]) => (init as RequestInit).headers)).toEqual([
      expect.objectContaining({ 'X-CSRF-Token': 'initial' }),
      expect.objectContaining({ 'X-CSRF-Token': 'recovered-two' }),
      expect.objectContaining({ 'X-CSRF-Token': 'recovered-three' }),
    ]);
  });
  it('ends pending logout on an owned SESSION_REQUIRED recheck', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok(session())).mockResolvedValueOnce(ok({ businesses: [] })).mockRejectedValueOnce(new TypeError('lost')).mockResolvedValueOnce(fail(401, 'SESSION_REQUIRED'));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/);
    await user.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(await screen.findByText(/Выход подтверждён текущей проверкой/)).toBeVisible();
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/auth/logout'))).toHaveLength(1);
  });
  it('does not start a fourth logout after a third ambiguous attempt', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok(session('one'))).mockResolvedValueOnce(ok({ businesses: [] })).mockRejectedValueOnce(new TypeError('lost-1')).mockResolvedValueOnce(ok(session('two'))).mockRejectedValueOnce(new TypeError('lost-2')).mockResolvedValueOnce(ok(session('three'))).mockRejectedValueOnce(new TypeError('lost-3'));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/);
    await user.click(screen.getByRole('button', { name: 'Выйти' })); await screen.findByText('Состояние сессии неизвестно');
    await user.click(screen.getByRole('button', { name: 'Проверить снова' })); await screen.findByText('Состояние сессии неизвестно');
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/auth/logout'))).toHaveLength(3);
  });
  it('keeps pending logout uncertain when recovery is offline', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok(session())).mockResolvedValueOnce(ok({ businesses: [] })).mockRejectedValueOnce(new TypeError('lost')).mockRejectedValueOnce(new TypeError('offline'));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/);
    await user.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(await screen.findByText('Состояние сессии неизвестно')).toBeVisible();
    expect(screen.queryByText(/Выход выполнен/)).not.toBeInTheDocument();
  });
  it('hands busy ownership to anonymous login after an owned Business SESSION_REQUIRED', async () => {
    const business = deferred<Response>(); const rotation = deferred<Response>();
    let businessCalls = 0; let rotationSignal: AbortSignal | undefined;
    const fetch = vi.fn((url: URL | RequestInfo, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/auth/session')) return Promise.resolve(ok(session('old')));
      if (path.includes('/businesses')) { businessCalls++; return businessCalls === 1 ? business.promise : Promise.resolve(ok({ businesses: [] })); }
      if (path.endsWith('/auth/rotate')) { rotationSignal = init?.signal as AbortSignal; return rotation.promise; }
      if (path.endsWith('/auth/bootstrap')) return Promise.resolve(ok(bootstrap('login-challenge')));
      if (path.endsWith('/auth/login')) return Promise.resolve(ok({ ...session('login-csrf'), user_account_id: '77777777-7777-4777-8777-777777777777' }));
      throw new Error(`unexpected test path: ${path}`);
    });
    vi.stubGlobal('fetch', fetch); const user = userEvent.setup(); render(<App />);
    await screen.findByText(/Пользователь/); await user.click(screen.getByRole('button', { name: 'Обновить защиту сессии' }));
    await waitFor(() => expect(rotationSignal).toBeDefined());
    business.resolve(fail(401, 'SESSION_REQUIRED'));
    const submit = await screen.findByRole('button', { name: 'Войти' });
    expect(submit).toBeEnabled(); expect(rotationSignal?.aborted).toBe(true); expect(screen.queryByText('ACTIVE SESSION')).not.toBeInTheDocument();
    rotation.resolve(ok(session('late-rotation')));
    await act(async () => { await rotation.promise; });
    expect(submit).toBeEnabled(); expect(screen.queryByText('Входим…')).not.toBeInTheDocument(); expect(businessCalls).toBe(1);
    await user.type(screen.getByLabelText('Логин'), 'owner.test'); await user.type(screen.getByLabelText('Пароль'), 'correct-password'); await user.click(submit);
    expect(await screen.findByText(/77777777/)).toBeVisible(); expect(businessCalls).toBe(2);
  });
  it('keeps the anonymous handoff after a late rotation rejection', async () => {
    const business = deferred<Response>(); const rotation = deferred<Response>(); let sessionReads = 0;
    const fetch = vi.fn((url: URL | RequestInfo) => {
      const path = String(url);
      if (path.endsWith('/auth/session')) { sessionReads++; return Promise.resolve(ok(session())); }
      if (path.includes('/businesses')) return business.promise;
      if (path.endsWith('/auth/rotate')) return rotation.promise;
      throw new Error(`unexpected test path: ${path}`);
    });
    vi.stubGlobal('fetch', fetch); const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/);
    await user.click(screen.getByRole('button', { name: 'Обновить защиту сессии' })); business.resolve(fail(401, 'SESSION_REQUIRED'));
    expect(await screen.findByRole('button', { name: 'Войти' })).toBeEnabled();
    rotation.reject(new TypeError('late rotation transport failure'));
    await act(async () => { await rotation.promise.catch(() => undefined); });
    expect(screen.getByText('Сессия завершена. Войдите снова.')).toBeVisible(); expect(sessionReads).toBe(1); expect(screen.getByRole('button', { name: 'Войти' })).toBeEnabled();
  });
  it('does not let a stale rotation finally unlock the next login', async () => {
    const business = deferred<Response>(); const rotation = deferred<Response>(); const login = deferred<Response>(); let loginCalls = 0;
    const fetch = vi.fn((url: URL | RequestInfo) => {
      const path = String(url);
      if (path.endsWith('/auth/session')) return Promise.resolve(ok(session()));
      if (path.includes('/businesses')) return business.promise;
      if (path.endsWith('/auth/rotate')) return rotation.promise;
      if (path.endsWith('/auth/bootstrap')) return Promise.resolve(ok(bootstrap()));
      if (path.endsWith('/auth/login')) { loginCalls++; return login.promise; }
      throw new Error(`unexpected test path: ${path}`);
    });
    vi.stubGlobal('fetch', fetch); const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/);
    await user.click(screen.getByRole('button', { name: 'Обновить защиту сессии' })); business.resolve(fail(401, 'SESSION_REQUIRED'));
    await screen.findByRole('button', { name: 'Войти' }); await user.type(screen.getByLabelText('Логин'), 'owner.test'); await user.type(screen.getByLabelText('Пароль'), 'correct-password');
    await user.dblClick(screen.getByRole('button', { name: 'Войти' })); await waitFor(() => expect(loginCalls).toBe(1));
    rotation.resolve(ok(session('stale'))); await act(async () => { await rotation.promise; });
    expect(screen.getByRole('button', { name: 'Входим…' })).toBeDisabled(); expect(loginCalls).toBe(1);
    login.resolve(ok({ ...session('fresh'), user_account_id: '88888888-8888-4888-8888-888888888888' })); expect(await screen.findByText(/88888888/)).toBeVisible();
  });
  it('ignores an old Business 401 after accepting a rotated session', async () => {
    const oldBusiness = deferred<Response>(); let businessCalls = 0;
    const fetch = vi.fn((url: URL | RequestInfo) => {
      const path = String(url);
      if (path.endsWith('/auth/session')) return Promise.resolve(ok(session('old')));
      if (path.includes('/businesses')) { businessCalls++; return businessCalls === 1 ? oldBusiness.promise : Promise.resolve(ok({ businesses: [] })); }
      if (path.endsWith('/auth/rotate')) return Promise.resolve(ok({ ...session('fresh'), user_account_id: '99999999-9999-4999-8999-999999999999' }));
      throw new Error(`unexpected test path: ${path}`);
    });
    vi.stubGlobal('fetch', fetch); const user = userEvent.setup(); render(<App />); await screen.findByText(/Пользователь/);
    await user.click(screen.getByRole('button', { name: 'Обновить защиту сессии' })); expect(await screen.findByText(/99999999/)).toBeVisible();
    oldBusiness.resolve(fail(401, 'SESSION_REQUIRED')); await act(async () => { await oldBusiness.promise; });
    expect(screen.getByText(/99999999/)).toBeVisible(); expect(screen.queryByRole('heading', { name: 'Вход в консоль' })).not.toBeInTheDocument(); expect(businessCalls).toBe(2);
  });
  it('keeps the latest session when an older success and error settle late, then mutates with latest CSRF', async () => {
    const initial = deferred<Response>(); const initialBusiness = deferred<Response>();
    const oldRead = deferred<Response>(); const newerRead = deferred<Response>();
    let sessionReads = 0; let businessReads = 0;
    const fetch = vi.fn((url: URL | RequestInfo, _init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/auth/session')) { sessionReads++; return [initial.promise, oldRead.promise, newerRead.promise][sessionReads - 1]; }
      if (path.includes('/businesses')) { businessReads++; return businessReads === 1 ? initialBusiness.promise : Promise.resolve(ok({ businesses: [] })); }
      if (path.endsWith('/auth/rotate')) return Promise.resolve(ok(session('latest')));
      throw new Error(`unexpected test path: ${path}`);
    });
    const visibility = Object.getOwnPropertyDescriptor(document, 'visibilityState');
    const listener = vi.spyOn(window, 'addEventListener');
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    try {
      vi.stubGlobal('fetch', fetch); render(<App />);
      expect(sessionReads).toBe(1);
      await act(async () => { initial.resolve(ok(session('initial'))); await initial.promise; });
      await screen.findByText(/Пользователь/); await waitFor(() => expect(businessReads).toBe(1));
      await act(async () => { initialBusiness.resolve(ok({ businesses: [] })); await initialBusiness.promise; });
      expect(listener.mock.calls.filter(([type]) => type === 'focus')).toHaveLength(2);

      fireEvent.focus(window); await waitFor(() => expect(sessionReads).toBe(2));
      fireEvent.focus(window); await waitFor(() => expect(sessionReads).toBe(3));
      await act(async () => { newerRead.resolve(ok({ ...session('latest'), user_account_id: '77777777-7777-4777-8777-777777777777' })); await newerRead.promise; });
      expect(await screen.findByText(/77777777/)).toBeVisible();
      await act(async () => { oldRead.resolve(ok({ ...session('stale'), user_account_id: uid })); await oldRead.promise; });
      expect(screen.getByText(/77777777/)).toBeVisible(); expect(screen.queryByText(uid)).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Обновить защиту сессии' })); await screen.findByText(/Защита сессии обновлена/);
      const rotate = fetch.mock.calls.find(([url]) => String(url).endsWith('/auth/rotate'));
      expect(rotate?.[1]).toMatchObject({ headers: expect.objectContaining({ 'X-CSRF-Token': 'latest' }) });
    } finally {
      listener.mockRestore();
      if (visibility) Object.defineProperty(document, 'visibilityState', visibility); else delete (document as { visibilityState?: string }).visibilityState;
    }
  });
  it('ignores stale session errors and late success after sign-out or unmount', async () => {
    const initial = deferred<Response>(); const initialBusiness = deferred<Response>();
    const staleError = deferred<Response>(); const newerRead = deferred<Response>(); const preLogout = deferred<Response>();
    let sessionReads = 0; let businessReads = 0;
    const fetch = vi.fn((url: URL | RequestInfo) => {
      const path = String(url);
      if (path.endsWith('/auth/session')) { sessionReads++; return [initial.promise, staleError.promise, newerRead.promise, preLogout.promise][sessionReads - 1]; }
      if (path.includes('/businesses')) { businessReads++; return businessReads === 1 ? initialBusiness.promise : Promise.resolve(ok({ businesses: [] })); }
      if (path.endsWith('/auth/logout')) return Promise.resolve(ok(null, 204));
      throw new Error(`unexpected test path: ${path}`);
    });
    const visibility = Object.getOwnPropertyDescriptor(document, 'visibilityState');
    const listener = vi.spyOn(window, 'addEventListener');
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    let view: ReturnType<typeof render> | undefined;
    try {
      vi.stubGlobal('fetch', fetch); const user = userEvent.setup(); view = render(<App />);
      expect(sessionReads).toBe(1);
      await act(async () => { initial.resolve(ok(session())); await initial.promise; });
      await screen.findByText(/Пользователь/); await waitFor(() => expect(businessReads).toBe(1));
      await act(async () => { initialBusiness.resolve(ok({ businesses: [] })); await initialBusiness.promise; });
      expect(listener.mock.calls.filter(([type]) => type === 'focus')).toHaveLength(2);

      fireEvent.focus(window); await waitFor(() => expect(sessionReads).toBe(2));
      fireEvent.focus(window); await waitFor(() => expect(sessionReads).toBe(3));
      await act(async () => { newerRead.resolve(ok({ ...session('newest'), user_account_id: '88888888-8888-4888-8888-888888888888' })); await newerRead.promise; });
      expect(await screen.findByText(/88888888/)).toBeVisible();
      const staleFailure = new TypeError('stale failure');
      await act(async () => { staleError.reject(staleFailure); await expect(staleError.promise).rejects.toBe(staleFailure); });
      expect(screen.queryByText('Состояние сессии неизвестно')).not.toBeInTheDocument();

      const logoutButton = screen.getByRole('button', { name: 'Выйти' });
      act(() => { fireEvent.focus(window); expect(sessionReads).toBe(4); logoutButton.click(); });
      await screen.findByText(/Выход выполнен/);
      const readsAtLogout = businessReads;
      await act(async () => { preLogout.resolve(ok({ ...session('too-late'), user_account_id: '99999999-9999-4999-8999-999999999999' })); await preLogout.promise; });
      expect(screen.queryByText(/99999999/)).not.toBeInTheDocument(); expect(screen.queryByText('ACTIVE SESSION')).not.toBeInTheDocument(); expect(businessReads).toBe(readsAtLogout);
      view.unmount(); view = undefined;
    } finally {
      view?.unmount(); listener.mockRestore();
      if (visibility) Object.defineProperty(document, 'visibilityState', visibility); else delete (document as { visibilityState?: string }).visibilityState;
    }
  });
  it('ignores a session success after unmount even when the double ignores AbortSignal', async () => {
    const late = deferred<Response>();
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => late.promise));
    const view = render(<App />); view.unmount(); late.resolve(ok(session('unmounted')));
    await late.promise;
    expect(document.body).not.toHaveTextContent('unmounted');
  });
});

describe('Ops shell', () => {
  it('keeps readiness and contains no tenant data', async () => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ status: 'ok', component: 'database' }))); render(<App pathname="/ops/" />); expect(await screen.findByText('Проверка готовности пройдена')).toBeVisible(); expect(screen.queryByText(uid)).not.toBeInTheDocument(); });
  it('does not accept invalid readiness or offline responses', async () => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ status: 'invented' }))); render(<App pathname="/ops/" />); expect(await screen.findByText('Сервис недоступен или не готов')).toBeVisible(); });
});

import { messagingApi, type Conversation } from './messaging-api';
import { controlApi, type ControlContext } from './conversation-control-api';
import { humanContextApi, type HumanContextState } from './human-context-api';
import { configurationApi, knowledgeApi } from './configuration-api';
import { PortfolioError, portfolioApi } from './portfolio-api';
import { business as fixtureBusiness, session as fixtureSession, draft as fixtureDraft, active as fixtureActive, preview as fixturePreview, knowledgeState as fixtureKnowledge } from './configuration-fixtures.test-helper';
import { ownerState, referenceState, conversationId, clientId, assetId } from './portfolio-fixtures.test-helper';

describe('selected conversation portfolio integration',()=>{
  let mode:'HUMAN'|'AI',barrier:boolean;
  const otherWorkspace='c1111111-1111-4111-8111-111111111111';
  const selectedConversation=(id=conversationId,client=clientId,business=bid):Conversation=>({conversation_id:id,connection_id:assetId,business_id:business,client_id:client,created_at:'2030-01-01T00:00:00.000000Z',version:'1',reply_window_expires_at:null});
  const currentReference=(w=wid,b=bid,id=conversationId,client=clientId)=>({...referenceState(),workspace_id:w,business_id:b,conversation_id:id,client_id:client,media_pin:{...referenceState().media_pin,business_id:b,conversation_id:id,client_id:client},portfolio_pin:{...referenceState().portfolio_pin,business_id:b}});
  const control=(c:ControlContext)=>({workspace_id:c.workspace,conversation_id:c.conversation,client_id:c.client,control_mode:mode,control_generation:'1',context_version:'1',observed_at:'2030-01-01T00:00:00.000000Z',manual_delivery:{has_dispatching:false,has_unknown:false}});
  const native=(c:ControlContext):HumanContextState=>({...control(c),policy:barrier?'PAUSED':'OFF_UNUSED',policy_epoch:barrier?'1':'0',observation_epoch:'0',ingress_checkpoint:'0',input_state_hash:'a'.repeat(64),input_gap_limit_exceeded:false,has_unsequenced_context_input:false,current_revision:null,review_status:barrier?'POLICY_PAUSED':'POLICY_INACTIVE',context_blockers:barrier?['POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED']:['POLICY_INACTIVE'],resume_blockers:barrier?['POLICY_PAUSED','HUMAN_REQUIRED','CONTEXT_CONFIRMATION_REQUIRED']:[],history_truncated:false,coverage_status:'UNCONFIRMED',pending_context_input:false,has_failed_context_input:false,unreviewed_failed_context_input:false,automation_work:{state:'IDLE',reason:null,job_id:null,turn_id:null,observed_at:'2030-01-01T00:00:00.000000Z'}});
  beforeEach(()=>{
    mode='HUMAN';barrier=false;messagingIntegration.enabled=true;
    vi.spyOn(api,'session').mockResolvedValue(fixtureSession());vi.spyOn(api,'businesses').mockImplementation(async w=>[{...fixtureBusiness(),workspace_id:w},{...fixtureBusiness(),workspace_id:w,id:assetId,name:'Другой бизнес'}]);vi.spyOn(api,'business').mockImplementation(async(w,id)=>({...fixtureBusiness(),workspace_id:w,id,name:id===bid?'Тестовая мастерская':'Другой бизнес'}));
    vi.spyOn(messagingApi,'connections').mockResolvedValue({items:[],next_cursor:null});vi.spyOn(messagingApi,'conversations').mockResolvedValue({items:[selectedConversation(),selectedConversation(assetId,assetId,assetId)],next_cursor:null});vi.spyOn(messagingApi,'messages').mockResolvedValue({items:[],next_cursor:null});vi.spyOn(messagingApi,'send');
    vi.spyOn(controlApi,'read').mockImplementation(async c=>control(c));vi.spyOn(controlApi,'command');vi.spyOn(humanContextApi,'read').mockImplementation(async c=>native(c));vi.spyOn(humanContextApi,'observations').mockResolvedValue({items:[],next_cursor:null,through_epoch:'0',current_epoch:'0',observed_at:'2030-01-01T00:00:00.000000Z'});vi.spyOn(humanContextApi,'reconcile');
    vi.spyOn(configurationApi,'draft').mockImplementation(async(w,b)=>({...fixtureDraft(),workspace_id:w,business_id:b}));vi.spyOn(configurationApi,'active').mockImplementation(async(w,b)=>({...fixtureActive(),workspace_id:w,business_id:b}));vi.spyOn(configurationApi,'preview').mockImplementation(async(w,b)=>fixturePreview({...fixtureDraft(),workspace_id:w,business_id:b}));vi.spyOn(knowledgeApi,'state').mockImplementation(async(w,b)=>({...fixtureKnowledge(),workspace_id:w,business_id:b}));vi.spyOn(portfolioApi,'state').mockImplementation(async(w,b)=>({...ownerState(),workspace_id:w,business_id:b}));
    vi.spyOn(portfolioApi,'conversation').mockImplementation(async(w,b,id,client)=>currentReference(w,b,id,client));vi.spyOn(portfolioApi,'analysis');vi.spyOn(portfolioApi,'matches').mockResolvedValue(currentReference());
  });
  afterEach(()=>{messagingIntegration.enabled=false;vi.restoreAllMocks();});
  async function open(){render(<App/>);await screen.findByText('Работа с графическим цветком.');}
  it('reads the server-selected client/Business in HUMAN without selecting a global Business or starting any POST',async()=>{
    await open();expect(configurationApi.draft).not.toHaveBeenCalled();expect(portfolioApi.conversation).toHaveBeenCalledWith(wid,bid,conversationId,clientId,expect.any(AbortSignal));expect(screen.getByRole('button',{name:'Подобрать подтверждённые работы'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'}));await waitFor(()=>expect(messagingApi.messages).toHaveBeenCalledTimes(2));fireEvent.click(screen.getByRole('button',{name:'Обновить референс и подбор'}));await waitFor(()=>expect(vi.mocked(portfolioApi.conversation).mock.calls.length).toBeGreaterThan(1));
    expect(portfolioApi.analysis).not.toHaveBeenCalled();expect(portfolioApi.matches).not.toHaveBeenCalled();expect(controlApi.command).not.toHaveBeenCalled();expect(humanContextApi.reconcile).not.toHaveBeenCalled();expect(messagingApi.send).not.toHaveBeenCalled();
  });
  it('follows two trusted conversation rows across Businesses regardless of the global Business selection',async()=>{
    await open();fireEvent.click(screen.getByRole('button',{name:/Другой бизнес/}));await screen.findByRole('heading',{name:'Настройки: Другой бизнес'});expect(screen.getByText('Работа с графическим цветком.')).toBeVisible();expect(vi.mocked(portfolioApi.conversation).mock.calls.at(-1)?.slice(0,4)).toEqual([wid,bid,conversationId,clientId]);
    fireEvent.click(screen.getByTestId(`conversation-${assetId}`));await waitFor(()=>expect(portfolioApi.conversation).toHaveBeenCalledWith(wid,assetId,assetId,assetId,expect.any(AbortSignal)));fireEvent.click(screen.getByRole('button',{name:/Тестовая мастерская/}));await screen.findByRole('heading',{name:'Настройки: Тестовая мастерская'});expect(vi.mocked(portfolioApi.conversation).mock.calls.at(-1)?.slice(0,4)).toEqual([wid,assetId,assetId,assetId]);expect(portfolioApi.analysis).not.toHaveBeenCalled();
  });
  it.each(['conversation','workspace'] as const)('discards a late old reference after changing %s',async change=>{
    const late=deferred<ReturnType<typeof currentReference>>();vi.mocked(portfolioApi.conversation).mockReturnValueOnce(late.promise);vi.mocked(api.session).mockResolvedValue({...fixtureSession(),memberships:[...fixtureSession().memberships,{workspace_id:otherWorkspace,role:'OWNER',permissions:[]}]});if(change==='workspace')vi.mocked(messagingApi.conversations).mockImplementation(async w=>({items:[w===wid?selectedConversation():selectedConversation(assetId,assetId,assetId)],next_cursor:null}));
    render(<App/>);await waitFor(()=>expect(portfolioApi.conversation).toHaveBeenCalled());if(change==='workspace')fireEvent.change(screen.getByLabelText('Workspace'),{target:{value:otherWorkspace}});else fireEvent.click(screen.getByTestId(`conversation-${assetId}`));await waitFor(()=>expect(portfolioApi.conversation).toHaveBeenCalledWith(change==='workspace'?otherWorkspace:wid,assetId,assetId,assetId,expect.any(AbortSignal)));
    await act(async()=>late.resolve({...currentReference(),matches:{...currentReference().matches!,matches:[{...currentReference().matches!.matches[0],text:'Устаревший приватный результат'}]}}));expect(screen.queryByText('Устаревший приватный результат')).toBeNull();expect(portfolioApi.analysis).not.toHaveBeenCalled();expect(portfolioApi.matches).not.toHaveBeenCalled();
  });
  it('enables an explicit AI action only after existing context gates, with no MODEL on mount',async()=>{
    mode='AI';vi.mocked(portfolioApi.conversation).mockImplementation(async(w,b,id,client)=>({...currentReference(w,b,id,client),embedding_mode:'CONTROLLED'}));await open();await waitFor(()=>expect(screen.getByRole('button',{name:'Подобрать подтверждённые работы'})).toBeEnabled());expect(portfolioApi.matches).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Подобрать подтверждённые работы'}));await waitFor(()=>expect(portfolioApi.matches).toHaveBeenCalledTimes(1));expect(controlApi.command).not.toHaveBeenCalled();
  });
  it('keeps derived observations readable while native barriers block new model actions',async()=>{
    mode='AI';barrier=true;vi.mocked(portfolioApi.conversation).mockImplementation(async(w,b,id,client)=>({...currentReference(w,b,id,client),embedding_mode:'CONTROLLED'}));await open();expect(screen.getByRole('button',{name:'Подобрать подтверждённые работы'})).toBeDisabled();expect(screen.getByText('Размер неизвестен')).toBeVisible();expect(portfolioApi.matches).not.toHaveBeenCalled();expect(controlApi.command).not.toHaveBeenCalled();
  });
  it('hides reference and all owner views on live OWNER denial and ignores late reads after OWNER loss',async()=>{
    await open();vi.mocked(portfolioApi.conversation).mockRejectedValueOnce(new PortfolioError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить референс и подбор'}));await screen.findByText('Нет доступа к данным владельца');expect(screen.queryByRole('region',{name:'Референс и подходящие работы'})).toBeNull();expect(screen.queryByText('Работа с графическим цветком.')).toBeNull();expect(portfolioApi.analysis).not.toHaveBeenCalled();
  });
});
