// Closed M5.1A owner API. Server validation and live OWNER remain authoritative.
export type IntakeField = { id: string; label: string; required: boolean };
export type Service = { id: string; name: string; description: string; active: boolean; intake_fields: IntakeField[]; price: { mode: string; amount_minor: number | null; formula_note: string | null }; duration: { mode: string; minutes: number | null; rule_note: string | null }; deposit: { mode: string; amount_minor: number | null; percent: number | null } };
export type Rule = { id: string; service_id: string | null; kind: string; value: number | boolean };
export type FAQ = { id: string; service_id: string | null; question: string; answer: string; source: string; confirmed: boolean; rule_ids: string[] };
export type Bundle = { schema_version: 1; communication_style: string; services: Service[]; rules: Rule[]; faqs: FAQ[] };
export type DraftState = { schema_version: 1; workspace_id: string; business_id: string; draft_version: string; activation_version: string; release_id: string | null; bundle: Bundle | null };
export type ActiveProjection = { schema_version: 1; workspace_id: string; business_id: string; activation_version: string; release_id: string | null; source_draft_version: string | null; published_by: string | null; published_at: string | null; bundle: Bundle | null; structured_rules_authoritative: true };
export type ValidationIssue = { severity: 'ERROR' | 'WARNING'; code: string; path: string };
export type Preview = { state: DraftState; validation: { valid: boolean; issues: ValidationIssue[] }; services: { service_id: string; active: boolean; owner_handoff: boolean }[]; structured_rules_authoritative: true };
export type EditDraft = { expected_draft_version: string; bundle: Bundle };
export type Publish = { expected_draft_version: string; expected_activation_version: string };
export type Rollback = { expected_activation_version: string; release_id: string };
export type Operation = 'EDIT' | 'PUBLISH' | 'ROLLBACK';
export type CommandBody = EditDraft | Publish | Rollback;
export type CommandResponse = { outcome: 'ACCEPTED' | 'REPLAY'; result: { workspace_id: string; business_id: string; receipt_id: string; operation: Operation; draft_version: string; release_id: string | null; activation_version: string; recorded_at: string } };
export class ConfigurationError extends Error { constructor(public status: number, public code: string) { super(code); } }
const invalid = (): never => { throw new ConfigurationError(502, 'INVALID_RESPONSE'); };
const object = (v: unknown, keys: string[]) => {
  if (typeof v !== 'object' || v === null || Array.isArray(v) || Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v, k))) return invalid();
  return v as Record<string, unknown>;
};
const text = (v: unknown, n: number, required = false): v is string => typeof v === 'string' && [...v].length <= n && (!required || !!v.trim()) && ![...v].some(c => { const x = c.codePointAt(0)!; return x === 0 || (x >= 0xd800 && x <= 0xdfff); });
const slug = (v: unknown): v is string => typeof v === 'string' && /^[a-z][a-z0-9_-]{0,39}$(?![\s\S])/.test(v);
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/.test(v);
const version = (v: unknown, zero = false): v is string => typeof v === 'string' && (zero ? /^(0|[1-9][0-9]{0,18})$(?![\s\S])/ : /^[1-9][0-9]{0,18}$(?![\s\S])/).test(v) && BigInt(v) <= 9223372036854775807n;
const number = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= 100000000000;
const nullable = (v: unknown, check: (x: unknown) => boolean) => v === null || check(v);
function items(v: unknown, n: number): unknown[] { if (!Array.isArray(v) || v.length > n) invalid(); return v as unknown[]; }
function timestamp(v: unknown): v is string { return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$(?![\s\S])/.test(v) && !v.startsWith('0000') && !Number.isNaN(new Date(v).valueOf()) && new Date(v).toISOString() === v.slice(0, 23) + 'Z'; }
function service(value: unknown): Service {
  const s = object(value, ['id','name','description','active','intake_fields','price','duration','deposit']);
  if (!slug(s.id) || !text(s.name,100,true) || !text(s.description,500) || typeof s.active !== 'boolean') invalid();
  for (const field of items(s.intake_fields,6)) { const f=object(field,['id','label','required']); if (!slug(f.id)||!text(f.label,100,true)||typeof f.required!=='boolean') invalid(); }
  for (const [name, keys] of [['price',['mode','amount_minor','formula_note']],['duration',['mode','minutes','rule_note']],['deposit',['mode','amount_minor','percent']]] as const) {
    const p=object(s[name],[...keys]); if (!text(p.mode,32,true)) invalid();
    for (const [key,v] of Object.entries(p)) if (key!=='mode' && !nullable(v, key.endsWith('_note') ? x=>text(x,160) : number)) invalid();
  }
  return s as Service;
}
export function parseBundle(value: unknown): Bundle {
  const b=object(value,['schema_version','communication_style','services','rules','faqs']);
  if (b.schema_version!==1||!text(b.communication_style,32,true)) invalid();
  const services=items(b.services,8).map(service);
  for (const value of items(b.rules,12)) { const r=object(value,['id','service_id','kind','value']); if (!slug(r.id)||!nullable(r.service_id,slug)||!text(r.kind,32,true)||!(typeof r.value==='boolean'||number(r.value))) invalid(); }
  for (const value of items(b.faqs,12)) { const f=object(value,['id','service_id','question','answer','source','confirmed','rule_ids']); if(!slug(f.id)||!nullable(f.service_id,slug)||!text(f.question,200,true)||!text(f.answer,500,true)||!text(f.source,120)||typeof f.confirmed!=='boolean'||!items(f.rule_ids,6).every(slug)) invalid(); }
  // Match the PostgreSQL jsonb::text byte envelope, including separators.
  const pgText=JSON.stringify(b).replace(/"(?:[^"\\]|\\.)*"|[:,]/g,match=>match===','?', ':match===':'?': ':match);
  if(new TextEncoder().encode(pgText).length>4096) invalid();
  return { ...b,services } as Bundle;
}
export function parseDraft(value: unknown): DraftState {
  const v=object(value,['schema_version','workspace_id','business_id','draft_version','activation_version','release_id','bundle']);
  if(v.schema_version!==1||!uuid(v.workspace_id)||!uuid(v.business_id)||!version(v.draft_version,true)||!version(v.activation_version,true)||!nullable(v.release_id,uuid)||(v.draft_version==='0')!==(v.bundle===null)||(v.activation_version==='0')!==(v.release_id===null))invalid();
  if(v.bundle!==null)parseBundle(v.bundle); return v as DraftState;
}
export function parseActive(value: unknown): ActiveProjection {
  const v=object(value,['schema_version','workspace_id','business_id','activation_version','release_id','source_draft_version','published_by','published_at','bundle','structured_rules_authoritative']);
  if(v.schema_version!==1||!uuid(v.workspace_id)||!uuid(v.business_id)||!version(v.activation_version,true)||!nullable(v.release_id,uuid)||v.structured_rules_authoritative!==true)invalid();
  const data=[v.source_draft_version,v.published_by,v.published_at,v.bundle];
  if(v.release_id===null){if(v.activation_version!=='0'||data.some(x=>x!==null))invalid();}
  else {if(v.activation_version==='0'||!version(v.source_draft_version)||!uuid(v.published_by)||!timestamp(v.published_at))invalid();parseBundle(v.bundle);}
  return v as ActiveProjection;
}
export function parsePreview(value: unknown): Preview {
  const v=object(value,['state','validation','services','structured_rules_authoritative']); const state=parseDraft(v.state); const validation=object(v.validation,['valid','issues']);
  const codes=['INVALID_SHAPE','INVALID_STYLE','NO_ACTIVE_SERVICE','DUPLICATE_ID','INVALID_MODE','INVALID_POLICY','INVALID_REFERENCE','INVALID_RULE','CONFLICTING_RULES','UNCONFIRMED_FAQ','OWNER_HANDOFF'];
  const issues=items(validation.issues,128).map(value=>{const i=object(value,['severity','code','path']);if(!['ERROR','WARNING'].includes(String(i.severity))||!codes.includes(String(i.code))||!text(i.path,200))invalid();return i as ValidationIssue;});
  if(typeof validation.valid!=='boolean'||validation.valid===issues.some(i=>i.severity==='ERROR')||v.structured_rules_authoritative!==true)invalid();
  for(const value of items(v.services,8)){const s=object(value,['service_id','active','owner_handoff']);if(!slug(s.service_id)||typeof s.active!=='boolean'||typeof s.owner_handoff!=='boolean')invalid();}
  return {...v,state,validation:{valid:validation.valid,issues}} as Preview;
}
export function parseCommand(value: unknown): CommandResponse {
  const v=object(value,['outcome','result']);const r=object(v.result,['workspace_id','business_id','receipt_id','operation','draft_version','release_id','activation_version','recorded_at']);
  if(!['ACCEPTED','REPLAY'].includes(String(v.outcome))||!uuid(r.workspace_id)||!uuid(r.business_id)||!uuid(r.receipt_id)||!['EDIT','PUBLISH','ROLLBACK'].includes(String(r.operation))||!version(r.draft_version)||!nullable(r.release_id,uuid)||!version(r.activation_version,true)||!timestamp(r.recorded_at)||(r.activation_version==='0')!==(r.release_id===null))invalid();
  return v as CommandResponse;
}
export function parseConfigurationError(value: unknown,status: number): ConfigurationError {
  const e=object(object(value,['error']).error,['code']);
  const codes:Record<number,string[]>={401:['SESSION_REQUIRED'],403:['ACCESS_DENIED','CSRF_REJECTED','ORIGIN_DENIED'],404:['NOT_FOUND'],409:['STALE_STATE','IDEMPOTENCY_KEY_CONFLICT','VALIDATION_FAILED','VERSION_EXHAUSTED','ROLLBACK_NOT_ALLOWED'],413:['BODY_TOO_LARGE'],415:['UNSUPPORTED_MEDIA_TYPE'],422:['INVALID_INPUT','INVALID_REQUEST'],429:['RATE_LIMITED'],500:['INTERNAL_ERROR'],503:['UNAVAILABLE']};
  if(typeof e.code!=='string'||!codes[status]?.includes(e.code))invalid();return new ConfigurationError(status,e.code as string);
}
async function request<T extends { workspace_id: string; business_id: string } | Preview | CommandResponse>(workspace: string,business: string,suffix: string,parser:(value:unknown)=>T,init:RequestInit,signal?:AbortSignal):Promise<T>{
  const controller=new AbortController(),abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();const timer=setTimeout(abort,10000);
  try{const response=await fetch(`/api/v1/workspaces/${encodeURIComponent(workspace)}/businesses/${encodeURIComponent(business)}/configuration/${suffix}`,{...init,credentials:'include',cache:'no-store',signal:controller.signal});let raw:unknown;try{raw=await response.json();}catch{invalid();}if(response.status!==200)throw parseConfigurationError(raw,response.status);const result=parser(raw);const scope: {workspace_id:string;business_id:string}='state'in result?(result as Preview).state:'result'in result?(result as CommandResponse).result:result as {workspace_id:string;business_id:string};if(scope.workspace_id!==workspace||scope.business_id!==business)invalid();return result;}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export function validateCommand(operation:Operation,body:CommandBody):void{
  if(operation==='EDIT'){const b=object(body,['expected_draft_version','bundle']);if(!version(b.expected_draft_version,true))invalid();parseBundle(b.bundle);}
  else if(operation==='PUBLISH'){const b=object(body,['expected_draft_version','expected_activation_version']);if(!version(b.expected_draft_version,true)||!version(b.expected_activation_version,true))invalid();}
  else{const b=object(body,['expected_activation_version','release_id']);if(!version(b.expected_activation_version,true)||!uuid(b.release_id))invalid();}
  if(new TextEncoder().encode(JSON.stringify(body)).length>4096)throw new ConfigurationError(413,'BODY_TOO_LARGE');
}
export const configurationApi={
  draft:(workspace:string,business:string,signal?:AbortSignal)=>request(workspace,business,'draft',parseDraft,{},signal),
  active:(workspace:string,business:string,signal?:AbortSignal)=>request(workspace,business,'active',parseActive,{},signal),
  preview:(workspace:string,business:string,signal?:AbortSignal)=>request(workspace,business,'preview',parsePreview,{},signal),
  async command(workspace:string,business:string,operation:Operation,body:CommandBody,key:string,csrf:string,signal?:AbortSignal){
    validateCommand(operation,body);if(!/^[A-Za-z0-9._:-]{1,128}$(?![\s\S])/.test(key))throw new ConfigurationError(422,'INVALID_INPUT');
    const result=await request(workspace,business,operation==='EDIT'?'draft':operation.toLowerCase(),parseCommand,{method:operation==='EDIT'?'PUT':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key},body:JSON.stringify(body)},signal);
    if(result.result.operation!==operation)invalid();return result;
  }
};
