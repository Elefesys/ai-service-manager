// R4 consumer boundary; schemas originate in contracts/openapi.json.
// Kept separate from the frozen M1.2 auth/Business parsers.
export type Decision = { key: string } & (
  { type: 'ENABLED'; reason: null; limit: null } |
  { type: 'DISABLED'; reason: 'SUBSCRIPTION_INACTIVE' | 'SERVICE_MODE_INACTIVE' | 'NOT_ENTITLED' | 'SERVICE_MODE_RESTRICTED'; limit: null } |
  { type: 'LIMIT'; reason: null; limit: string });
export type Billing = {
  workspace_id: string; evaluated_at: string;
  account: { billing_account_id: string; contact_display_name: string; version: string };
  subscription: null | { subscription_id: string; status: 'TRIALING' | 'ACTIVE'; funding_mode: 'TRIAL' | 'COMPED'; effective_from: string; effective_until: string; version: string; plan: { plan_id: string; code: string; revision_id: string; revision: number } };
  mode: 'NORMAL' | 'GRACE' | 'LIMITED' | 'SUSPENDED'; mode_active: boolean; availability: 'ACTIVE' | 'INACTIVE'; decisions: Decision[];
};
export type ContactBody = Readonly<{ expected_version: string; contact_display_name: string }>;
export type ContactResult = { workspace_id: string; billing_account_id: string; receipt_id: string; result_version: string; outcome: 'UPDATED' | 'NOOP'; completed_at: string };
export type AuditItem = { audit_event_id: string; occurred_at: string; correlation_id: string; object_type: 'WORKSPACE_BILLING_ACCOUNT'; object_id: string; object_version: string } & (
  { event_type: 'WORKSPACE_BILLING_PROVISIONED'; actor_kind: 'LOCAL_PROVISIONER'; actor_user_account_id: null; payload: Record<string, never> } |
  { event_type: 'BILLING_ACCOUNT_CONTACT_UPDATED'; actor_kind: 'USER_ACCOUNT'; actor_user_account_id: string; payload: { changed_fields: ['contact_display_name'] } });
export type AuditPage = { items: AuditItem[]; next_cursor: string | null };
export class BillingError extends Error {
  constructor(public status: number, public code: string, public stateReason?: string) { super(code); }
}
const invalid = (): never => { throw new BillingError(502, 'INVALID_RESPONSE'); };
function object(v: unknown, keys: string[]): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v) || Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v, k))) return invalid();
  return v as Record<string, unknown>;
}
const matches = (v: unknown, pattern: RegExp): v is string => typeof v === 'string' && pattern.test(v);
const uuid = (v: unknown) => matches(v, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/);
const oneOf = (v: unknown, values: readonly string[]) => typeof v === 'string' && values.includes(v);
const decimal = (v: unknown, zero = false) => matches(v, zero ? /^(0|[1-9][0-9]{0,18})$(?![\s\S])/ : /^[1-9][0-9]{0,18}$(?![\s\S])/) && BigInt(v) <= 9223372036854775807n;
function timestamp(v: unknown) {
  if (!matches(v, /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$(?![\s\S])/) || v.startsWith('0000')) return false;
  const date = new Date(v);
  return !Number.isNaN(date.valueOf()) && date.toISOString() === v.slice(0, 23) + 'Z';
}
export function normalizeContact(value: string): string {
  const name = value.replace(/^ +| +$(?![\s\S])/g, '');
  const scalars = [...name];
  if (scalars.length < 1 || scalars.length > 200 || scalars.some(c => { const n = c.codePointAt(0)!; return n < 32 || n === 127 || (n >= 0xd800 && n <= 0xdfff); }) || new TextEncoder().encode(name).length > 800) throw new BillingError(422, 'INVALID_REQUEST');
  return name;
}
function decision(value: unknown): Decision {
  const v = object(value, ['key', 'type', 'reason', 'limit']);
  if (!matches(v.key, /^[a-z][a-z0-9_.:-]{0,127}$(?![\s\S])/)) invalid();
  if (!(v.type === 'ENABLED' && v.reason === null && v.limit === null) && !(v.type === 'LIMIT' && v.reason === null && decimal(v.limit, true)) && !(v.type === 'DISABLED' && v.limit === null && oneOf(v.reason, ['SUBSCRIPTION_INACTIVE','SERVICE_MODE_INACTIVE','NOT_ENTITLED','SERVICE_MODE_RESTRICTED']))) invalid();
  return v as Decision;
}
export function parseBilling(value: unknown): Billing {
  const v = object(value, ['workspace_id','evaluated_at','account','subscription','mode','mode_active','availability','decisions']);
  const a = object(v.account, ['billing_account_id','contact_display_name','version']);
  if (!uuid(v.workspace_id) || !timestamp(v.evaluated_at) || !uuid(a.billing_account_id) || !decimal(a.version) || typeof a.contact_display_name !== 'string') invalid();
  try { if (normalizeContact(a.contact_display_name as string) !== a.contact_display_name) invalid(); } catch { invalid(); }
  if (v.subscription !== null) {
    const s = object(v.subscription, ['subscription_id','status','funding_mode','effective_from','effective_until','version','plan']);
    const p = object(s.plan, ['plan_id','code','revision_id','revision']);
    if (!uuid(s.subscription_id) || !decimal(s.version) || !timestamp(s.effective_from) || !timestamp(s.effective_until) || !((s.status === 'TRIALING' && s.funding_mode === 'TRIAL') || (s.status === 'ACTIVE' && s.funding_mode === 'COMPED')) || !uuid(p.plan_id) || !uuid(p.revision_id) || !matches(p.code, /^[a-z][a-z0-9_-]{0,63}$(?![\s\S])/) || !Number.isSafeInteger(p.revision) || (p.revision as number) < 1) invalid();
  }
  if (!oneOf(v.mode, ['NORMAL','GRACE','LIMITED','SUSPENDED']) || typeof v.mode_active !== 'boolean' || !oneOf(v.availability, ['ACTIVE','INACTIVE']) || !Array.isArray(v.decisions) || v.decisions.length > 100) invalid();
  const decisions = (v.decisions as unknown[]).map(decision);
  if (decisions.some((d, i) => i > 0 && decisions[i - 1].key >= d.key)) invalid();
  return { ...v, decisions } as Billing;
}
export function parseContactResult(value: unknown): ContactResult {
  const v = object(value, ['workspace_id','billing_account_id','receipt_id','result_version','outcome','completed_at']);
  if (!uuid(v.workspace_id) || !uuid(v.billing_account_id) || !uuid(v.receipt_id) || !decimal(v.result_version) || !oneOf(v.outcome, ['UPDATED','NOOP']) || !timestamp(v.completed_at)) invalid();
  return v as ContactResult;
}
function auditItem(value: unknown): AuditItem {
  const v = object(value, ['audit_event_id','occurred_at','event_type','actor_kind','actor_user_account_id','correlation_id','object_type','object_id','object_version','payload']);
  if (!uuid(v.audit_event_id) || !timestamp(v.occurred_at) || !uuid(v.correlation_id) || v.object_type !== 'WORKSPACE_BILLING_ACCOUNT' || !uuid(v.object_id) || !decimal(v.object_version)) invalid();
  if (v.event_type === 'WORKSPACE_BILLING_PROVISIONED' && v.actor_kind === 'LOCAL_PROVISIONER' && v.actor_user_account_id === null) object(v.payload, []);
  else if (v.event_type === 'BILLING_ACCOUNT_CONTACT_UPDATED' && v.actor_kind === 'USER_ACCOUNT' && uuid(v.actor_user_account_id)) {
    const p = object(v.payload, ['changed_fields']);
    if (!Array.isArray(p.changed_fields) || p.changed_fields.length !== 1 || p.changed_fields[0] !== 'contact_display_name') invalid();
  } else invalid();
  return v as AuditItem;
}
export function parseAuditPage(value: unknown): AuditPage {
  const v = object(value, ['items','next_cursor']);
  if (!Array.isArray(v.items) || v.items.length > 10 || !(v.next_cursor === null || matches(v.next_cursor, /^[A-Za-z0-9_-]{1,1024}$(?![\s\S])/))) invalid();
  return { items: (v.items as unknown[]).map(auditItem), next_cursor: v.next_cursor as string | null };
}
export function parseBillingError(value: unknown, status: number, structural: boolean): BillingError {
  const outer = object(value, ['error']);
  const detail = outer.error;
  if (structural && status === 503 && typeof detail === 'object' && detail !== null && 'code' in detail && detail.code === 'BILLING_STATE_UNAVAILABLE') {
    const e = object(detail, ['code','state_reason']);
    if (!oneOf(e.state_reason, ['BILLING_STATE_MISSING','BILLING_STATE_INVALID','REVISION_INVALID','DATABASE_UNAVAILABLE'])) invalid();
    return new BillingError(status, 'BILLING_STATE_UNAVAILABLE', e.state_reason as string);
  }
  const e = object(detail, ['code']);
  const codes: Record<number, string[]> = { 401: ['SESSION_REQUIRED'], 403: ['ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED'], 404: ['NOT_FOUND'], 409: ['STALE_STATE','IDEMPOTENCY_KEY_CONFLICT'], 413: ['BODY_TOO_LARGE'], 415: ['UNSUPPORTED_MEDIA_TYPE'], 422: ['INVALID_REQUEST'], 429: ['RATE_LIMITED'], 500: ['INTERNAL_ERROR'], 503: ['UNAVAILABLE'] };
  if (!oneOf(e.code, codes[status] ?? [])) invalid();
  return new BillingError(status, e.code as string);
}
async function request<T>(workspace: string, path: string, parser: (value: unknown) => T, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const c = new AbortController();
  const abort = () => c.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) c.abort();
  const timer = setTimeout(abort, 10_000);
  try {
    const response = await fetch(`/api/v1/workspaces/${encodeURIComponent(workspace)}/${path}`, { ...init, credentials: 'include', cache: 'no-store', signal: c.signal });
    let value: unknown;
    try { value = await response.json(); } catch { return invalid(); }
    if (response.status !== 200) throw parseBillingError(value, response.status, path === 'billing');
    return parser(value);
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
export const billingApi = {
  async read(workspace: string, signal?: AbortSignal) {
    const result = await request(workspace, 'billing', parseBilling, {}, signal);
    if (result.workspace_id !== workspace) invalid();
    return result;
  },
  async save(workspace: string, body: ContactBody, key: string, csrf: string, signal?: AbortSignal) {
    const result = await request(workspace, 'billing-account', parseContactResult, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': key }, body: JSON.stringify(body) }, signal);
    if (result.workspace_id !== workspace) invalid();
    return result;
  },
  audit(workspace: string, cursor: string | null, signal?: AbortSignal) {
    return request(workspace, `audit-events?limit=10${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`, parseAuditPage, {}, signal);
  },
};
