// Strict consumer of the accepted OpenAPI / messaging.http_models contract.
// Auth/Business and billing parsers deliberately keep their existing boundaries.
export type Connection = { connection_id: string; business_id: string; provider: 'CONTROLLED' | 'TELEGRAM'; state: 'AVAILABLE' | 'DISABLED' | 'RIGHTS_MISSING' | 'UNVERIFIED' | 'UNAVAILABLE'; observed_at: string | null; created_at: string; version: string };
export type Conversation = { conversation_id: string; connection_id: string; business_id: string; client_id: string; created_at: string; version: string; reply_window_expires_at: string | null };
export type FileError = 'INVALID_INPUT' | 'DEPENDENCY_TIMEOUT' | 'DEPENDENCY_UNAVAILABLE' | 'RETRY_EXHAUSTED';
export type DeliveryError = FileError | 'NOT_ALLOWED' | 'UNKNOWN_EXTERNAL_RESULT';
export type ImageFile = { file_id: string; status: 'PENDING' | 'READY' | 'FAILED'; error_code: FileError | null; manifest: { mime_type: 'image/jpeg' | 'image/png' | 'image/webp'; size_bytes: string; width: number; height: number } | null };
export type Delivery = { status: 'PENDING' | 'DISPATCHING' | 'SENT' | 'FAILED' | 'UNKNOWN'; error_code: DeliveryError | null; completed_at: string | null; version: string };
export type Message = { message_id: string; conversation_id: string; direction: 'INBOUND' | 'OUTBOUND'; content_type: 'TEXT' | 'IMAGE_REFERENCE'; text: string | null; occurred_at: string; created_at: string; version: string; file: ImageFile | null; delivery: Delivery | null };
export type Page<T> = { items: T[]; next_cursor: string | null };
export type SendBody = Readonly<{ text: string }>;
export type SendReceipt = { workspace_id: string; receipt_id: string; message_id: string; accepted_at: string; outcome: 'ACCEPTED' | 'REPLAY' };
export type ReadGrant = { url: string; expires_at: string };
export class MessagingError extends Error {
  constructor(public status: number, public code: string, public stateReason?: string) { super(code); }
}
const invalid = (): never => { throw new MessagingError(502, 'INVALID_RESPONSE'); };
function object(v: unknown, keys: string[]): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v) || Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v, k))) return invalid();
  return v as Record<string, unknown>;
}
const matches = (v: unknown, p: RegExp): v is string => typeof v === 'string' && p.test(v);
const uuid = (v: unknown) => matches(v, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/);
const oneOf = (v: unknown, values: readonly string[]) => typeof v === 'string' && values.includes(v);
const decimal = (v: unknown): v is string => matches(v, /^[1-9][0-9]{0,18}$(?![\s\S])/) && BigInt(v) <= 9223372036854775807n;
function timestamp(v: unknown): v is string {
  if (!matches(v, /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$(?![\s\S])/) || v.startsWith('0000')) return false;
  const d = new Date(v);
  return !Number.isNaN(d.valueOf()) && d.toISOString() === v.slice(0, 23) + 'Z';
}
// Python str.isspace(), including U+001C..001F and U+0085, excluding BOM.
const whitespace = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$(?![\s\S])/;
export function exactManualText(value: string): string {
  const scalars = [...value];
  if (!scalars.length || scalars.length > 4096 || whitespace.test(value) || scalars.some(c => { const n = c.codePointAt(0)!; return n === 0 || (n >= 0xd800 && n <= 0xdfff); }) || new TextEncoder().encode(value).length > 16384) throw new MessagingError(422, 'INVALID_REQUEST');
  return value;
}
export function parseConnection(value: unknown): Connection {
  const v = object(value, ['connection_id','business_id','provider','state','observed_at','created_at','version']);
  if (!uuid(v.connection_id) || !uuid(v.business_id) || !oneOf(v.provider, ['CONTROLLED','TELEGRAM']) || !oneOf(v.state, ['AVAILABLE','DISABLED','RIGHTS_MISSING','UNVERIFIED','UNAVAILABLE']) || !(v.observed_at === null || timestamp(v.observed_at)) || !timestamp(v.created_at) || !decimal(v.version)) invalid();
  if (v.provider === 'CONTROLLED' && (v.observed_at !== null || !oneOf(v.state, ['AVAILABLE','DISABLED']))) invalid();
  return v as Connection;
}
export function parseConversation(value: unknown): Conversation {
  const v = object(value, ['conversation_id','connection_id','business_id','client_id','created_at','version','reply_window_expires_at']);
  if (!['conversation_id','connection_id','business_id','client_id'].every(k => uuid(v[k])) || !timestamp(v.created_at) || !decimal(v.version) || !(v.reply_window_expires_at === null || timestamp(v.reply_window_expires_at))) invalid();
  return v as Conversation;
}
const fileErrors = ['INVALID_INPUT','DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE','RETRY_EXHAUSTED'];
function parseFile(value: unknown): ImageFile {
  const v = object(value, ['file_id','status','error_code','manifest']);
  if (!uuid(v.file_id) || !oneOf(v.status, ['PENDING','READY','FAILED']) || !(v.error_code === null || oneOf(v.error_code, fileErrors)) || (v.status === 'READY') !== (v.manifest !== null) || (v.status === 'FAILED') !== (v.error_code !== null)) invalid();
  if (v.manifest !== null) {
    const m = object(v.manifest, ['mime_type','size_bytes','width','height']);
    if (!oneOf(m.mime_type, ['image/jpeg','image/png','image/webp']) || !decimal(m.size_bytes) || BigInt(m.size_bytes) > 10485760n || !Number.isInteger(m.width) || !Number.isInteger(m.height) || (m.width as number) < 1 || (m.height as number) < 1 || (m.width as number) > 8192 || (m.height as number) > 8192 || (m.width as number) * (m.height as number) > 20000000) invalid();
  }
  return v as ImageFile;
}
function parseDelivery(value: unknown): Delivery {
  const v = object(value, ['status','error_code','completed_at','version']);
  if (!oneOf(v.status, ['PENDING','DISPATCHING','SENT','FAILED','UNKNOWN']) || !decimal(v.version) || !(v.error_code === null || oneOf(v.error_code, [...fileErrors,'NOT_ALLOWED','UNKNOWN_EXTERNAL_RESULT'])) || !(v.completed_at === null || timestamp(v.completed_at))) invalid();
  if (oneOf(v.status, ['SENT','FAILED','UNKNOWN']) !== (v.completed_at !== null) || (v.status === 'SENT' && v.error_code !== null) || (oneOf(v.status, ['FAILED','UNKNOWN']) && v.error_code === null)) invalid();
  return v as Delivery;
}
export function parseMessage(value: unknown): Message {
  const v = object(value, ['message_id','conversation_id','direction','content_type','text','occurred_at','created_at','version','file','delivery']);
  if (!uuid(v.message_id) || !uuid(v.conversation_id) || !oneOf(v.direction, ['INBOUND','OUTBOUND']) || !oneOf(v.content_type, ['TEXT','IMAGE_REFERENCE']) || !(v.text === null || (typeof v.text === 'string' && [...v.text].length <= 4096)) || !timestamp(v.occurred_at) || !timestamp(v.created_at) || !decimal(v.version)) invalid();
  if ((v.content_type === 'IMAGE_REFERENCE') !== (v.file !== null) || (v.direction === 'OUTBOUND') !== (v.delivery !== null)) invalid();
  if (v.file !== null) parseFile(v.file);
  if (v.delivery !== null) parseDelivery(v.delivery);
  return v as Message;
}
export function parsePage<T>(value: unknown, parse: (v: unknown) => T): Page<T> {
  const v = object(value, ['items','next_cursor']);
  if (!Array.isArray(v.items) || v.items.length > 25 || !(v.next_cursor === null || matches(v.next_cursor, /^[A-Za-z0-9_-]{1,1024}$(?![\s\S])/))) invalid();
  return { items: (v.items as unknown[]).map(parse), next_cursor: v.next_cursor as string | null };
}
export function parseReceipt(value: unknown): SendReceipt {
  const v = object(value, ['workspace_id','receipt_id','message_id','accepted_at','outcome']);
  if (!uuid(v.workspace_id) || !uuid(v.receipt_id) || !uuid(v.message_id) || !timestamp(v.accepted_at) || !oneOf(v.outcome, ['ACCEPTED','REPLAY'])) invalid();
  return v as SendReceipt;
}
export function parseReadGrant(value: unknown): ReadGrant {
  const v = object(value, ['url','expires_at']);
  if (typeof v.url !== 'string' || !v.url || !timestamp(v.expires_at)) invalid();
  try {
    const u = new URL(v.url as string);
    const local = ['127.0.0.1','localhost','[::1]'].includes(u.hostname);
    if (u.username || u.password || (u.protocol !== 'https:' && !(u.protocol === 'http:' && local && window.location.protocol === 'http:'))) invalid();
  } catch { invalid(); }
  return v as ReadGrant; // Keep the signed bytes; never serialize the parsed URL.
}
export function parseMessagingError(value: unknown, status: number, send = false): MessagingError {
  const outer = object(value, ['error']);
  const detail = outer.error;
  if (send && status === 503 && typeof detail === 'object' && detail !== null && 'code' in detail && detail.code === 'BILLING_STATE_UNAVAILABLE') {
    const e = object(detail, ['code','state_reason']);
    if (!oneOf(e.state_reason, ['BILLING_STATE_MISSING','BILLING_STATE_INVALID','REVISION_INVALID','DATABASE_UNAVAILABLE'])) invalid();
    return new MessagingError(status, 'BILLING_STATE_UNAVAILABLE', e.state_reason as string);
  }
  const e = object(detail, ['code']);
  const codes: Record<number, string[]> = { 401: ['SESSION_REQUIRED'], 403: ['ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED'], 404: ['NOT_FOUND'], 409: ['IDEMPOTENCY_KEY_CONFLICT','NOT_ALLOWED'], 413: ['BODY_TOO_LARGE'], 415: ['UNSUPPORTED_MEDIA_TYPE'], 422: ['INVALID_REQUEST'], 429: ['RATE_LIMITED'], 500: ['INTERNAL_ERROR'], 503: ['UNAVAILABLE'] };
  if (!oneOf(e.code, codes[status] ?? [])) invalid();
  return new MessagingError(status, e.code as string);
}
async function request<T>(workspace: string, path: string, parse: (value: unknown) => T, init: RequestInit = {}, signal?: AbortSignal, send = false): Promise<T> {
  const c = new AbortController(), abort = () => c.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) c.abort();
  const timer = setTimeout(abort, 10000);
  try {
    const response = await fetch(`/api/v1/workspaces/${encodeURIComponent(workspace)}/${path}`, { ...init, credentials: 'include', cache: 'no-store', signal: c.signal });
    let value: unknown;
    try { value = await response.json(); } catch { return invalid(); }
    if (response.status !== (send ? 202 : 200)) throw parseMessagingError(value, response.status, send);
    return parse(value);
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
const pageQuery = (cursor: string | null) => `?limit=25${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`;
const historyPath = (conversation: string) => `conversations/${encodeURIComponent(conversation)}/messages`;
export const messagingApi = {
  connections(workspace: string, cursor: string | null, signal?: AbortSignal) { return request(workspace, `channel-connections${pageQuery(cursor)}`, v => parsePage(v, parseConnection), {}, signal); },
  conversations(workspace: string, cursor: string | null, signal?: AbortSignal) { return request(workspace, `conversations${pageQuery(cursor)}`, v => parsePage(v, parseConversation), {}, signal); },
  async messages(workspace: string, conversation: string, cursor: string | null, signal?: AbortSignal) {
    const page = await request(workspace, `${historyPath(conversation)}${pageQuery(cursor)}`, v => parsePage(v, parseMessage), {}, signal);
    if (page.items.some(m => m.conversation_id !== conversation)) invalid();
    return page;
  },
  async send(workspace: string, conversation: string, body: SendBody, key: string, csrf: string, signal?: AbortSignal) {
    const receipt = await request(workspace, historyPath(conversation), parseReceipt, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': key }, body: JSON.stringify(body) }, signal, true);
    if (receipt.workspace_id !== workspace) invalid();
    return receipt;
  },
  grant(workspace: string, conversation: string, message: string, file: string, csrf: string, signal?: AbortSignal) {
    return request(workspace, `${historyPath(conversation)}/${encodeURIComponent(message)}/files/${encodeURIComponent(file)}/read-grant`, parseReadGrant, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: '{}' }, signal);
  },
};
