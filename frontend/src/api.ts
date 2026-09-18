export type Bootstrap = { csrf_token: string; expires_at: string };
export type Membership = { workspace_id: string; role: 'OWNER' | 'ADMIN' | 'PROVIDER'; permissions: string[] };
export type Session = Bootstrap & { user_account_id: string; memberships: Membership[] };
export type Business = { workspace_id: string; id: string; name: string; status: string; version: number; created_at: string };
export type ErrorCode = 'INVALID_CREDENTIALS' | 'SESSION_REQUIRED' | 'ORIGIN_DENIED' | 'CSRF_REJECTED' | 'ACCESS_DENIED' | 'NOT_FOUND' | 'BODY_TOO_LARGE' | 'UNSUPPORTED_MEDIA_TYPE' | 'INVALID_REQUEST' | 'RATE_LIMITED' | 'UNAVAILABLE' | 'INTERNAL_ERROR';

export class ApiError extends Error {
  constructor(public status: number, public code: ErrorCode | 'INVALID_RESPONSE', public retryAfter?: string) { super(code); }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).length === keys.length && keys.every((key) => key in value);
const text = (value: unknown): value is string => typeof value === 'string';
const validDate = (value: unknown): value is string => text(value) && !Number.isNaN(Date.parse(value));
const invalid = (): never => { throw new ApiError(502, 'INVALID_RESPONSE'); };

export function parseBootstrap(value: unknown): Bootstrap {
  if (!record(value)) throw new ApiError(502, 'INVALID_RESPONSE');
  if (!exact(value, ['csrf_token', 'expires_at']) || !text(value.csrf_token) || !validDate(value.expires_at)) invalid();
  return value as Bootstrap;
}

export function parseSession(value: unknown): Session {
  if (!record(value)) throw new ApiError(502, 'INVALID_RESPONSE');
  if (!exact(value, ['user_account_id', 'expires_at', 'csrf_token', 'memberships']) || !text(value.user_account_id) || !uuid.test(value.user_account_id) || !validDate(value.expires_at) || !text(value.csrf_token) || !Array.isArray(value.memberships)) invalid();
  const memberships = (value.memberships as unknown[]).map((item): Membership => {
    if (!record(item) || !exact(item, ['workspace_id', 'role', 'permissions']) || !text(item.workspace_id) || !uuid.test(item.workspace_id) || !['OWNER', 'ADMIN', 'PROVIDER'].includes(String(item.role)) || !Array.isArray(item.permissions) || !item.permissions.every(text)) invalid();
    return item as Membership;
  });
  return { user_account_id: value.user_account_id as string, expires_at: value.expires_at as string, csrf_token: value.csrf_token as string, memberships };
}

export function parseBusiness(value: unknown): Business {
  if (!record(value)) throw new ApiError(502, 'INVALID_RESPONSE');
  if (!exact(value, ['workspace_id', 'id', 'name', 'status', 'version', 'created_at']) || !text(value.workspace_id) || !uuid.test(value.workspace_id) || !text(value.id) || !uuid.test(value.id) || !text(value.name) || !text(value.status) || !Number.isInteger(value.version) || !validDate(value.created_at)) invalid();
  return value as Business;
}

const errorCodes: ErrorCode[] = ['INVALID_CREDENTIALS','SESSION_REQUIRED','ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED','NOT_FOUND','BODY_TOO_LARGE','UNSUPPORTED_MEDIA_TYPE','INVALID_REQUEST','RATE_LIMITED','UNAVAILABLE','INTERNAL_ERROR'];

async function request(path: string, init: RequestInit, signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try { response = await fetch(`/api/v1${path}`, { ...init, cache: 'no-store', credentials: 'include', signal }); }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new TypeError('NETWORK'); }
  if (!response.ok) {
    let code: ErrorCode | 'INVALID_RESPONSE' = 'INVALID_RESPONSE';
    try { const body: unknown = await response.json(); if (record(body) && exact(body, ['error']) && record(body.error) && exact(body.error, ['code']) && errorCodes.includes(body.error.code as ErrorCode)) code = body.error.code as ErrorCode; } catch { /* invalid error remains fail-closed */ }
    throw new ApiError(response.status, code, response.headers.get('Retry-After') ?? undefined);
  }
  return response;
}

const jsonPost = (headers: HeadersInit = {}, body: unknown = {}): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
export const api = {
  async bootstrap(signal?: AbortSignal) { return parseBootstrap(await (await request('/auth/bootstrap', jsonPost({ 'X-CSRF-Bootstrap': '1' }), signal)).json()); },
  async login(login: string, password: string, csrf: string, signal?: AbortSignal) { return parseSession(await (await request('/auth/login', jsonPost({ 'X-CSRF-Token': csrf }, { login, password }), signal)).json()); },
  async session(signal?: AbortSignal) { return parseSession(await (await request('/auth/session', {}, signal)).json()); },
  async rotate(csrf: string, signal?: AbortSignal) { return parseSession(await (await request('/auth/rotate', jsonPost({ 'X-CSRF-Token': csrf }), signal)).json()); },
  async logout(csrf: string, signal?: AbortSignal) { await request('/auth/logout', jsonPost({ 'X-CSRF-Token': csrf }), signal); },
  async businesses(workspace: string, signal?: AbortSignal) { const value: unknown = await (await request(`/workspaces/${encodeURIComponent(workspace)}/businesses`, {}, signal)).json(); if (!record(value)) throw new ApiError(502, 'INVALID_RESPONSE'); if (!exact(value, ['businesses']) || !Array.isArray(value.businesses)) invalid(); return (value.businesses as unknown[]).map(parseBusiness); },
  async business(workspace: string, id: string, signal?: AbortSignal) { return parseBusiness(await (await request(`/workspaces/${encodeURIComponent(workspace)}/businesses/${encodeURIComponent(id)}`, {}, signal)).json()); },
};
