export type Membership = { workspace_id: string; role: 'OWNER' | 'ADMIN' | 'PROVIDER'; permissions: string[] };
export type Session = { user_account_id: string; expires_at: string; csrf_token: string; memberships: Membership[] };
export type Business = { workspace_id: string; id: string; name: string; status: string; version: number; created_at: string };
export type ErrorCode = 'INVALID_CREDENTIALS' | 'SESSION_REQUIRED' | 'ORIGIN_DENIED' | 'CSRF_REJECTED' | 'ACCESS_DENIED' | 'NOT_FOUND' | 'BODY_TOO_LARGE' | 'UNSUPPORTED_MEDIA_TYPE' | 'INVALID_REQUEST' | 'RATE_LIMITED' | 'UNAVAILABLE' | 'INTERNAL_ERROR';

export class ApiError extends Error {
  constructor(public status: number, public code: ErrorCode | 'INVALID_RESPONSE', public retryAfter?: string) { super(code); }
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).length === keys.length && keys.every((k) => k in v);
const text = (v: unknown): v is string => typeof v === 'string';
const validDate = (v: unknown): v is string => text(v) && !Number.isNaN(Date.parse(v));

export function parseSession(v: unknown): Session {
  if (!record(v) || !exact(v, ['user_account_id', 'expires_at', 'csrf_token', 'memberships']) || !text(v.user_account_id) || !uuid.test(v.user_account_id) || !validDate(v.expires_at) || !text(v.csrf_token) || !Array.isArray(v.memberships)) throw new ApiError(502, 'INVALID_RESPONSE');
  const memberships = v.memberships.map((item): Membership => {
    if (!record(item) || !exact(item, ['workspace_id', 'role', 'permissions']) || !text(item.workspace_id) || !uuid.test(item.workspace_id) || !['OWNER', 'ADMIN', 'PROVIDER'].includes(String(item.role)) || !Array.isArray(item.permissions) || !item.permissions.every(text)) throw new ApiError(502, 'INVALID_RESPONSE');
    return { workspace_id: item.workspace_id, role: item.role as Membership['role'], permissions: item.permissions };
  });
  return { user_account_id: v.user_account_id, expires_at: v.expires_at, csrf_token: v.csrf_token, memberships };
}
function parseBusiness(v: unknown): Business {
  if (!record(v) || !exact(v, ['workspace_id', 'id', 'name', 'status', 'version', 'created_at']) || !text(v.workspace_id) || !uuid.test(v.workspace_id) || !text(v.id) || !uuid.test(v.id) || !text(v.name) || !text(v.status) || !Number.isInteger(v.version) || !validDate(v.created_at)) throw new ApiError(502, 'INVALID_RESPONSE');
  return v as Business;
}
const errorCodes: ErrorCode[] = ['INVALID_CREDENTIALS','SESSION_REQUIRED','ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED','NOT_FOUND','BODY_TOO_LARGE','UNSUPPORTED_MEDIA_TYPE','INVALID_REQUEST','RATE_LIMITED','UNAVAILABLE','INTERNAL_ERROR'];

async function request(path: string, init: RequestInit, signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try { response = await fetch(`/api/v1${path}`, { ...init, credentials: 'include', signal }); }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new TypeError('NETWORK'); }
  if (!response.ok) {
    let code: ErrorCode | 'INVALID_RESPONSE' = 'INVALID_RESPONSE';
    try { const body: unknown = await response.json(); if (record(body) && exact(body, ['error']) && record(body.error) && exact(body.error, ['code']) && errorCodes.includes(body.error.code as ErrorCode)) code = body.error.code as ErrorCode; } catch { /* invalid error remains invalid */ }
    throw new ApiError(response.status, code, response.headers.get('Retry-After') ?? undefined);
  }
  return response;
}
const jsonPost = (headers: HeadersInit = {}, body: unknown = {}) => ({ method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
export const api = {
  async session(signal?: AbortSignal) { return parseSession(await (await request('/auth/session', {}, signal)).json()); },
  async bootstrap(signal?: AbortSignal) { return parseSession(await (await request('/auth/bootstrap', jsonPost({ 'X-CSRF-Bootstrap': '1' }), signal)).json()); },
  async login(login: string, password: string, csrf: string, signal?: AbortSignal) { return parseSession(await (await request('/auth/login', jsonPost({ 'X-CSRF-Token': csrf }, { login, password }), signal)).json()); },
  async rotate(csrf: string, signal?: AbortSignal) { return parseSession(await (await request('/auth/rotate', jsonPost({ 'X-CSRF-Token': csrf }), signal)).json()); },
  async logout(csrf: string, signal?: AbortSignal) { await request('/auth/logout', jsonPost({ 'X-CSRF-Token': csrf }), signal); },
  async businesses(workspace: string, signal?: AbortSignal) { const v: unknown = await (await request(`/workspaces/${encodeURIComponent(workspace)}/businesses`, {}, signal)).json(); if (!record(v) || !exact(v, ['businesses']) || !Array.isArray(v.businesses)) throw new ApiError(502, 'INVALID_RESPONSE'); return v.businesses.map(parseBusiness); },
  async business(workspace: string, id: string, signal?: AbortSignal) { return parseBusiness(await (await request(`/workspaces/${encodeURIComponent(workspace)}/businesses/${encodeURIComponent(id)}`, {}, signal)).json()); },
};
