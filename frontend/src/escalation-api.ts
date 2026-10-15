// Four accepted owner routes (M3_CONTRACT §14.5/14.16). Receipts are historical.
export type EscalationStatus = 'PENDING' | 'RESOLVED' | 'CANCELLED' | 'EXPIRED';
export type StatusFilter = EscalationStatus | 'ALL';
export type EscalationOperation = 'RESOLVE' | 'CANCEL';
export type EscalationContext = Readonly<{ workspace: string; escalation: string; conversation: string; client: string }>;
export type EscalationBody = Readonly<{ expected_conversation_id: string; expected_client_id: string; expected_escalation_version: string; expected_control_generation: string; expected_context_version: string; answer_text?: string }>;
type ClosureReason = 'OWNER_CANCELLED' | 'CONTROL_CHANGED' | 'CONTEXT_CHANGED' | 'ASSIGNEE_REVOKED' | 'DEADLINE_ELAPSED';
export type EscalationView = {
  workspace_id: string; escalation_id: string; conversation_id: string; client_id: string; turn_id: string; assignee_user_account_id: string;
  reason: 'OWNER_DECISION_REQUIRED'; question: 'CONTROLLED ESCALATION TEST: требуется решение владельца.'; policy: 'LOCAL_TEST_OWNER_WAIT_V1';
  version: '1' | '2'; status: EscalationStatus;
  bound_context: { turn_revision: string; control_generation: string; context_version: string; fingerprint: string };
  current_context: { control_mode: 'HUMAN' | 'AI'; control_generation: string; context_version: string };
  validity: 'CURRENT' | 'CONTROL_CHANGED' | 'CONTEXT_CHANGED' | 'ASSIGNEE_REVOKED' | 'EXPIRED' | 'TERMINAL'; waiting: 'WAITING_FOR_HUMAN' | null;
  created_at: string; due_at: string; second_reminder_at: string; expires_at: string; observed_at: string;
  reminders: { ordinal: 1 | 2; due_at: string; recorded_at: string | null }[];
  maintenance: 'SCHEDULED' | 'COMPLETE' | 'FAILED';
  resolution: { answer_text: string; actor_user_account_id: string; completed_at: string } | null;
  closure: { reason: ClosureReason; actor_user_account_id: string | null; completed_at: string } | null;
  can_resolve: boolean; can_cancel: boolean;
};
export type EscalationPage = { items: EscalationView[]; next_cursor: string | null; observed_at: string };
export type EscalationReceipt = { outcome: 'ACCEPTED' | 'REPLAY'; result: {
  workspace_id: string; escalation_id: string; conversation_id: string; client_id: string; receipt_id: string; audit_event_id: string;
  operation: EscalationOperation; accepted_status: 'RESOLVED' | 'CANCELLED'; previous_version: '1'; accepted_version: '2';
  accepted_context_version: string; control_generation: string; accepted_at: string;
} };
export class EscalationError extends Error { constructor(public status: number, public code: string) { super(code); } }
const invalid = (): never => { throw new EscalationError(502, 'INVALID_RESPONSE'); };
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value) || Object.keys(value).length !== keys.length || !keys.every(k => Object.hasOwn(value,k))) return invalid();
  return value as Record<string, unknown>;
}
const matches = (v: unknown, re: RegExp): v is string => typeof v === 'string' && re.test(v);
const uuid = (v: unknown) => matches(v,/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/);
const decimal = (v: unknown) => matches(v,/^[1-9][0-9]{0,18}$(?![\s\S])/) && BigInt(v) <= 9223372036854775807n;
const oneOf = (v: unknown, choices: string[]) => typeof v === 'string' && choices.includes(v);
function timestamp(v: unknown) {
  if (!matches(v,/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$(?![\s\S])/) || v.startsWith('0000')) return false;
  const d = new Date(v);
  return !Number.isNaN(d.valueOf()) && d.toISOString() === v.slice(0,23)+'Z';
}
export function exactAnswer(value: unknown): string {
  // Python's str.strip whitespace set; validation only, never transform text.
  if (typeof value !== 'string' || [...value].length < 1 || [...value].length > 512 || /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(value) || /[\u0000\uD800-\uDFFF]/u.test(value) || new TextEncoder().encode(value).length > 2048) throw new EscalationError(422,'INVALID_REQUEST');
  return value;
}
export function parseEscalation(value: unknown, workspace: string, expected?: Partial<Omit<EscalationContext,'workspace'>>): EscalationView {
  const v = object(value,['workspace_id','escalation_id','conversation_id','client_id','turn_id','assignee_user_account_id','reason','question','policy','version','status','bound_context','current_context','validity','waiting','created_at','due_at','second_reminder_at','expires_at','observed_at','reminders','maintenance','resolution','closure','can_resolve','can_cancel']);
  if (!['workspace_id','escalation_id','conversation_id','client_id','turn_id','assignee_user_account_id'].every(k=>uuid(v[k])) || v.workspace_id !== workspace || (expected?.escalation !== undefined && v.escalation_id !== expected.escalation) || (expected?.conversation !== undefined && v.conversation_id !== expected.conversation) || (expected?.client !== undefined && v.client_id !== expected.client)) invalid();
  const bound = object(v.bound_context,['turn_revision','control_generation','context_version','fingerprint']);
  const current = object(v.current_context,['control_mode','control_generation','context_version']);
  if (!['turn_revision','control_generation','context_version'].every(k=>decimal(bound[k])) || !matches(bound.fingerprint,/^[0-9a-f]{64}$(?![\s\S])/) || !decimal(current.control_generation) || !decimal(current.context_version) || !oneOf(current.control_mode,['AI','HUMAN'])) invalid();
  if (v.reason !== 'OWNER_DECISION_REQUIRED' || v.question !== 'CONTROLLED ESCALATION TEST: требуется решение владельца.' || v.policy !== 'LOCAL_TEST_OWNER_WAIT_V1' || !oneOf(v.status,['PENDING','RESOLVED','CANCELLED','EXPIRED']) || !oneOf(v.validity,['CURRENT','CONTROL_CHANGED','CONTEXT_CHANGED','ASSIGNEE_REVOKED','EXPIRED','TERMINAL']) || !oneOf(v.maintenance,['SCHEDULED','COMPLETE','FAILED']) || typeof v.can_resolve !== 'boolean' || typeof v.can_cancel !== 'boolean' || !['created_at','due_at','second_reminder_at','expires_at','observed_at'].every(k=>timestamp(v[k]))) invalid();
  if (!Array.isArray(v.reminders) || v.reminders.length !== 2) invalid();
  (v.reminders as unknown[]).forEach((raw,i)=>{
    const r=object(raw,['ordinal','due_at','recorded_at']);
    if (r.ordinal !== i+1 || r.due_at !== v[i===0?'due_at':'second_reminder_at'] || (r.recorded_at !== null && !timestamp(r.recorded_at))) invalid();
  });
  const pending=v.status==='PENDING', active=pending&&v.validity==='CURRENT';
  if (v.version !== (pending?'1':'2') || (v.validity==='TERMINAL')===pending || v.waiting !== (active?'WAITING_FOR_HUMAN':null) || (v.resolution !== null)!==(v.status==='RESOLVED') || (v.closure !== null)!==oneOf(v.status,['CANCELLED','EXPIRED']) || !(String(v.created_at)<String(v.due_at)&&String(v.due_at)<String(v.second_reminder_at)&&String(v.second_reminder_at)<String(v.expires_at)) || (v.can_resolve&&!active) || (v.can_cancel&&(!pending||!oneOf(v.validity,['CURRENT','ASSIGNEE_REVOKED'])||String(v.observed_at)>=String(v.expires_at)))) invalid();
  if (v.resolution !== null) {
    const r=object(v.resolution,['answer_text','actor_user_account_id','completed_at']);
    try { exactAnswer(r.answer_text); } catch { invalid(); }
    if (!uuid(r.actor_user_account_id)||!timestamp(r.completed_at)) invalid();
  }
  if (v.closure !== null) {
    const c=object(v.closure,['reason','actor_user_account_id','completed_at']);
    if (!oneOf(c.reason,['OWNER_CANCELLED','CONTROL_CHANGED','CONTEXT_CHANGED','ASSIGNEE_REVOKED','DEADLINE_ELAPSED']) || !timestamp(c.completed_at) || (c.reason==='OWNER_CANCELLED'?!uuid(c.actor_user_account_id):c.actor_user_account_id!==null) || (v.status==='EXPIRED')!==(c.reason==='DEADLINE_ELAPSED')) invalid();
  }
  return v as EscalationView;
}
export function parseEscalationPage(value: unknown, workspace: string, status: StatusFilter, limit=10): EscalationPage {
  const v=object(value,['items','next_cursor','observed_at']);
  if (!Array.isArray(v.items)||v.items.length>limit||!timestamp(v.observed_at)||(v.next_cursor!==null&&(!matches(v.next_cursor,/^[A-Za-z0-9_-]+$(?![\s\S])/ )||v.next_cursor.length>1024))) invalid();
  const items=(v.items as unknown[]).map(item=>parseEscalation(item,workspace));
  if (items.some(item=>item.observed_at!==v.observed_at||(status!=='ALL'&&item.status!==status)) || new Set(items.map(item=>item.escalation_id)).size!==items.length) invalid();
  return {items,next_cursor:v.next_cursor as string|null,observed_at:v.observed_at as string};
}
export function parseEscalationReceipt(value: unknown, context: EscalationContext, operation: EscalationOperation, body: EscalationBody): EscalationReceipt {
  const v=object(value,['outcome','result']);
  const r=object(v.result,['workspace_id','escalation_id','conversation_id','client_id','receipt_id','audit_event_id','operation','accepted_status','previous_version','accepted_version','accepted_context_version','control_generation','accepted_at']);
  if (!oneOf(v.outcome,['ACCEPTED','REPLAY'])||!['workspace_id','escalation_id','conversation_id','client_id','receipt_id','audit_event_id'].every(k=>uuid(r[k])) || r.workspace_id!==context.workspace || r.escalation_id!==context.escalation || r.conversation_id!==context.conversation || r.client_id!==context.client || r.operation!==operation || r.accepted_status!==(operation==='RESOLVE'?'RESOLVED':'CANCELLED') || r.previous_version!=='1'||r.accepted_version!=='2'||!decimal(r.accepted_context_version)||!decimal(r.control_generation)||!timestamp(r.accepted_at)) invalid();
  if (body.expected_conversation_id!==r.conversation_id || body.expected_client_id!==r.client_id || body.expected_escalation_version!==r.previous_version || body.expected_control_generation!==r.control_generation || !decimal(body.expected_context_version) || BigInt(r.accepted_context_version as string)!==BigInt(body.expected_context_version)+1n) invalid();
  return v as EscalationReceipt;
}
export function parseEscalationError(value: unknown, status: number): EscalationError {
  const e=object(object(value,['error']).error,['code']);
  const codes: Record<number,string[]>={401:['SESSION_REQUIRED'],403:['ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED'],404:['NOT_FOUND'],409:['IDEMPOTENCY_KEY_CONFLICT','STALE_STATE','ESCALATION_EXPIRED','ESCALATION_FINAL','VERSION_EXHAUSTED'],413:['BODY_TOO_LARGE'],415:['UNSUPPORTED_MEDIA_TYPE'],422:['INVALID_REQUEST'],429:['RATE_LIMITED'],500:['INTERNAL_ERROR'],503:['UNAVAILABLE']};
  if (typeof e.code!=='string'||!codes[status]?.includes(e.code)) invalid();
  return new EscalationError(status,e.code as string);
}
async function request<T>(workspace: string, suffix: string, parse: (v: unknown)=>T, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const c=new AbortController(), abort=()=>c.abort();
  signal?.addEventListener('abort',abort,{once:true}); if(signal?.aborted)c.abort();
  const timer=setTimeout(abort,10000);
  try {
    const response=await fetch(`/api/v1/workspaces/${encodeURIComponent(workspace)}/escalations${suffix}`,{...init,credentials:'include',cache:'no-store',signal:c.signal});
    let value: unknown; try {value=await response.json();} catch {return invalid();}
    if(response.status!==200)throw parseEscalationError(value,response.status);
    return parse(value);
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export const escalationApi={
  list(workspace: string, status: StatusFilter='PENDING', cursor: string|null=null, signal?: AbortSignal) {return request(workspace,`?limit=10&status=${status}${cursor===null?'':`&cursor=${encodeURIComponent(cursor)}`}`,v=>parseEscalationPage(v,workspace,status),{},signal);},
  read(context: EscalationContext, signal?: AbortSignal) {return request(context.workspace,`/${encodeURIComponent(context.escalation)}`,v=>parseEscalation(v,context.workspace,context),{},signal);},
  command(context: EscalationContext, operation: EscalationOperation, body: EscalationBody, key: string, csrf: string, signal?: AbortSignal) {
    return request(context.workspace,`/${encodeURIComponent(context.escalation)}/${operation==='RESOLVE'?'resolve':'cancel'}`,v=>parseEscalationReceipt(v,context,operation,body),{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key},body:JSON.stringify(body)},signal);
  },
};
