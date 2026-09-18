import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, parseBootstrap, parseBusiness, parseSession } from './api';

const accountV4 = '11111111-1111-4111-8111-111111111111';
const workspaceV7 = '22222222-2222-7222-8222-222222222222';
const businessV4 = '33333333-3333-4333-8333-333333333333';
const businessV7 = '44444444-4444-7444-8444-444444444444';
const expires = '2030-01-01T00:00:00Z';
const bootstrap = { csrf_token: 'bootstrap-csrf', expires_at: expires };
const session = { ...bootstrap, user_account_id: accountV4, memberships: [{ workspace_id: workspaceV7, role: 'OWNER', permissions: ['tenancy:read'] }] };
const business = (id = businessV7) => ({ workspace_id: workspaceV7, id, name: 'API business', status: 'ACTIVE', version: 1, created_at: expires });
const response = (body: unknown, status = 200, headers?: HeadersInit) => new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });

afterEach(() => vi.unstubAllGlobals());

describe('auth DTO consumers', () => {
  it('accepts the exact two-field BootstrapResponse only', () => {
    expect(parseBootstrap(bootstrap)).toEqual(bootstrap);
    for (const value of [
      { csrf_token: 'x' },
      { ...bootstrap, expires_at: 'invalid' },
      { ...bootstrap, user_account_id: accountV4 },
      { ...bootstrap, memberships: [] },
    ]) expect(() => parseBootstrap(value)).toThrowError(new ApiError(502, 'INVALID_RESPONSE'));
  });

  it('supports UUIDv4 and UUIDv7 in every accepted identity position', () => {
    expect(parseSession(session).memberships[0].workspace_id).toBe(workspaceV7);
    expect(parseSession({ ...session, user_account_id: '55555555-5555-7555-8555-555555555555' }).user_account_id).toContain('-7');
    expect(parseBusiness(business(businessV4)).id).toBe(businessV4);
    expect(parseBusiness(business()).id).toBe(businessV7);
  });

  it('rejects malformed UUIDs, unsupported versions, extra fields, and malformed nested DTOs', () => {
    const invalid = [
      { ...session, user_account_id: 'not-a-uuid' },
      { ...session, user_account_id: '11111111-1111-5111-8111-111111111111' },
      { ...session, extra: true },
      { ...session, memberships: [{ ...session.memberships[0], workspace_id: 'bad' }] },
      { ...session, memberships: [{ ...session.memberships[0], permissions: [1] }] },
    ];
    invalid.forEach((value) => expect(() => parseSession(value)).toThrow('INVALID_RESPONSE'));
    expect(() => parseBusiness({ ...business(), workspace_id: 'bad' })).toThrow('INVALID_RESPONSE');
  });
});

describe('seven endpoint consumer contract', () => {
  it('uses exact success DTOs, credentials, no-store, JSON and current CSRF headers', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(response(bootstrap))
      .mockResolvedValueOnce(response(session))
      .mockResolvedValueOnce(response(session))
      .mockResolvedValueOnce(response({ ...session, csrf_token: 'rotated' }))
      .mockResolvedValueOnce(response(null, 204))
      .mockResolvedValueOnce(response({ businesses: [business()] }))
      .mockResolvedValueOnce(response(business()));
    vi.stubGlobal('fetch', fetch);

    const challenge = await api.bootstrap();
    const loggedIn = await api.login(' owner.test ', '  unchanged password  ', challenge.csrf_token);
    await api.session();
    await api.rotate(loggedIn.csrf_token);
    await api.logout('rotated');
    await api.businesses(workspaceV7);
    await api.business(workspaceV7, businessV7);

    expect(fetch).toHaveBeenCalledTimes(7);
    for (const [, init] of fetch.mock.calls) expect(init).toMatchObject({ cache: 'no-store', credentials: 'include' });
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/auth/bootstrap', '/api/v1/auth/login', '/api/v1/auth/session', '/api/v1/auth/rotate', '/api/v1/auth/logout',
      `/api/v1/workspaces/${workspaceV7}/businesses`, `/api/v1/workspaces/${workspaceV7}/businesses/${businessV7}`,
    ]);
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST', headers: expect.objectContaining({ 'Content-Type': 'application/json', 'X-CSRF-Bootstrap': '1' }), body: '{}' });
    expect(fetch.mock.calls[1][1]).toMatchObject({ method: 'POST', headers: expect.objectContaining({ 'X-CSRF-Token': 'bootstrap-csrf' }) });
    expect(JSON.parse(String(fetch.mock.calls[1][1].body))).toEqual({ login: ' owner.test ', password: '  unchanged password  ' });
    expect(fetch.mock.calls[2][1].method).toBeUndefined();
    expect(fetch.mock.calls[3][1]).toMatchObject({ method: 'POST', headers: expect.objectContaining({ 'X-CSRF-Token': 'bootstrap-csrf' }), body: '{}' });
    expect(fetch.mock.calls[4][1]).toMatchObject({ method: 'POST', headers: expect.objectContaining({ 'X-CSRF-Token': 'rotated' }), body: '{}' });
  });

  it('sends login once after bootstrap and distinguishes server credentials from client shape errors', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response(bootstrap)).mockResolvedValueOnce(response({ error: { code: 'INVALID_CREDENTIALS' } }, 401));
    vi.stubGlobal('fetch', fetch);
    const challenge = await api.bootstrap();
    await expect(api.login('owner.test', 'wrong password unchanged', challenge.csrf_token)).rejects.toMatchObject({ status: 401, code: 'INVALID_CREDENTIALS' });
    expect(fetch.mock.calls.filter(([path]) => path === '/api/v1/auth/login')).toHaveLength(1);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...bootstrap, memberships: [] })));
    await expect(api.bootstrap()).rejects.toMatchObject({ status: 502, code: 'INVALID_RESPONSE' });
  });

  it('maps strict error envelopes and Retry-After without trusting malformed errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ error: { code: 'RATE_LIMITED' } }, 429, { 'Retry-After': '30' })));
    await expect(api.session()).rejects.toMatchObject({ status: 429, code: 'RATE_LIMITED', retryAfter: '30' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ error: { code: 'INVENTED', detail: 'unsafe' } }, 403)));
    await expect(api.session()).rejects.toMatchObject({ status: 403, code: 'INVALID_RESPONSE' });
  });
});
