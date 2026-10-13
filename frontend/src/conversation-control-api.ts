// Consumer of the accepted CONTROL http_models/OpenAPI; receipt != current state.
export type ControlMode = 'HUMAN' | 'AI';
export type ControlOperation = 'TAKEOVER' | 'RESUME';
export type ControlContext = Readonly<{ workspace: string; conversation: string; client: string }>;
export type ControlBody = Readonly<{ expected_client_id: string; expected_control_generation: string; expected_context_version: string }>;
export type ControlState = {
  workspace_id: string; conversation_id: string; client_id: string;
  control_mode: ControlMode; control_generation: string; context_version: string; observed_at: string;
  manual_delivery: { has_dispatching: boolean; has_unknown: boolean };
};
export type ControlReceipt = { outcome: 'ACCEPTED' | 'REPLAY'; result: {
  workspace_id: string; conversation_id: string; client_id: string; receipt_id: string; audit_event_id: string;
  operation: ControlOperation; previous_mode: ControlMode; accepted_mode: ControlMode;
  previous_generation: string; accepted_generation: string; context_version: string; accepted_at: string;
} };
export class ControlError extends Error {
  constructor(public status: number, public code: string, public stateReason?: string) { super(code); }
}
const invalid = (): never => { throw new ControlError(502, 'INVALID_RESPONSE'); };
function object(v: unknown, keys: string[]): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v) || Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v,k))) return invalid();
  return v as Record<string, unknown>;
}
const matches = (v: unknown, re: RegExp): v is string => typeof v === 'string' && re.test(v);
const uuid = (v: unknown) => matches(v,/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/);
const version = (v: unknown) => matches(v,/^[1-9][0-9]{0,18}$(?![\s\S])/) && BigInt(v) <= 9223372036854775807n;
const mode = (v: unknown) => v === 'HUMAN' || v === 'AI';
function timestamp(v: unknown) {
  if (!matches(v,/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$(?![\s\S])/) || v.startsWith('0000')) return false;
  const d = new Date(v);
  return !Number.isNaN(d.valueOf()) && d.toISOString() === v.slice(0,23)+'Z';
}
function identity(v: Record<string, unknown>, context: ControlContext) {
  if (!uuid(v.workspace_id) || !uuid(v.conversation_id) || !uuid(v.client_id) || v.workspace_id !== context.workspace || v.conversation_id !== context.conversation || v.client_id !== context.client) invalid();
}
export function parseControlState(value: unknown, context: ControlContext): ControlState {
  const v = object(value,['workspace_id','conversation_id','client_id','control_mode','control_generation','context_version','observed_at','manual_delivery']);
  identity(v,context);
  const delivery = object(v.manual_delivery,['has_dispatching','has_unknown']);
  if (!mode(v.control_mode) || !version(v.control_generation) || !version(v.context_version) || !timestamp(v.observed_at) || typeof delivery.has_dispatching !== 'boolean' || typeof delivery.has_unknown !== 'boolean') invalid();
  return v as ControlState;
}
export function parseControlReceipt(value: unknown, context: ControlContext, operation: ControlOperation, body: ControlBody): ControlReceipt {
  const v = object(value,['outcome','result']);
  const r = object(v.result,['workspace_id','conversation_id','client_id','receipt_id','audit_event_id','operation','previous_mode','accepted_mode','previous_generation','accepted_generation','context_version','accepted_at']);
  identity(r,context);
  if ((v.outcome !== 'ACCEPTED' && v.outcome !== 'REPLAY') || !uuid(r.receipt_id) || !uuid(r.audit_event_id) || r.operation !== operation || !mode(r.previous_mode) || r.accepted_mode !== (operation === 'TAKEOVER' ? 'HUMAN' : 'AI') || !version(r.previous_generation) || !version(r.accepted_generation) || !version(r.context_version) || !timestamp(r.accepted_at)) invalid();
  if (BigInt(r.accepted_generation as string) !== BigInt(r.previous_generation as string)+1n || r.previous_generation !== body.expected_control_generation || r.context_version !== body.expected_context_version || r.client_id !== body.expected_client_id) invalid();
  return v as ControlReceipt;
}
export function parseControlError(value: unknown, status: number): ControlError {
  const v = object(value,['error']);
  if (status === 503 && typeof v.error === 'object' && v.error !== null && 'code' in v.error && v.error.code === 'BILLING_STATE_UNAVAILABLE') {
    const e = object(v.error,['code','state_reason']);
    if (typeof e.state_reason !== 'string' || !['BILLING_STATE_MISSING','BILLING_STATE_INVALID','REVISION_INVALID','DATABASE_UNAVAILABLE'].includes(e.state_reason)) invalid();
    return new ControlError(status,'BILLING_STATE_UNAVAILABLE',e.state_reason as string);
  }
  const e = object(v.error,['code']);
  const codes: Record<number,string[]> = {401:['SESSION_REQUIRED'],403:['ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED'],404:['NOT_FOUND'],409:['IDEMPOTENCY_KEY_CONFLICT','STALE_STATE','NOT_ALLOWED','CONTROL_VERSION_EXHAUSTED'],413:['BODY_TOO_LARGE'],415:['UNSUPPORTED_MEDIA_TYPE'],422:['INVALID_REQUEST'],429:['RATE_LIMITED'],500:['INTERNAL_ERROR'],503:['UNAVAILABLE']};
  if (typeof e.code !== 'string' || !codes[status]?.includes(e.code)) invalid();
  return new ControlError(status,e.code as string);
}
async function request<T>(context: ControlContext, route: string, parse: (v: unknown) => T, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const c = new AbortController(), abort = () => c.abort();
  signal?.addEventListener('abort',abort,{once:true}); if (signal?.aborted) c.abort();
  const timer = setTimeout(abort,10000);
  try {
    const response = await fetch(`/api/v1/workspaces/${encodeURIComponent(context.workspace)}/conversations/${encodeURIComponent(context.conversation)}/${route}`,{...init,credentials:'include',cache:'no-store',signal:c.signal});
    let value: unknown;
    try { value = await response.json(); } catch { return invalid(); }
    if (response.status !== 200) throw parseControlError(value,response.status);
    return parse(value);
  } finally { clearTimeout(timer); signal?.removeEventListener('abort',abort); }
}
export const controlApi = {
  read(context: ControlContext, signal?: AbortSignal) { return request(context,'control',v=>parseControlState(v,context),{},signal); },
  command(context: ControlContext, operation: ControlOperation, body: ControlBody, key: string, csrf: string, signal?: AbortSignal) {
    return request(context,operation === 'TAKEOVER' ? 'takeover' : 'resume',v=>parseControlReceipt(v,context,operation,body),{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key},body:JSON.stringify(body)},signal);
  },
};
