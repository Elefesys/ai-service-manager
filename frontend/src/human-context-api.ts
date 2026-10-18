// Exact consumer of native_context_http_models/OpenAPI at the accepted 0013 source.
import type { ControlContext } from './conversation-control-api';
export type Disposition = 'OWNER_TEXT' | 'CANONICAL_SUFFICIENT' | 'UNRESOLVED';
export type SourceMedia = 'NONE' | 'UNAVAILABLE';
export const blockerOrder = ['POLICY_INACTIVE','POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_CHANGED','CONTEXT_UNRESOLVED','NEW_OBSERVATION','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED','CONTEXT_INPUT_PENDING'] as const;
export type ContextBlocker = typeof blockerOrder[number];
export type Coverage = 'UNCONFIRMED' | 'UNRESOLVED' | 'OWNER_TEXT' | 'CANONICAL_COMPLETE' | 'CANONICAL_TRUNCATED';
export type ContextHold = {reason:'CONTEXT_POLICY_PAUSED'|'CONTEXT_CONFIRMATION_REQUIRED'|'CONTEXT_UNRESOLVED'|'NEW_OBSERVATION'|'CONTEXT_INPUT_UNRESOLVED'|'CONTEXT_COVERAGE_REQUIRED'|'CONTEXT_INPUT_PENDING';policy:'ON'|'PAUSED';policy_epoch:string;observation_epoch:string;coverage_status:Coverage};
export type Revision = {revision_id:string;revision_no:string;previous_revision_id:string|null;actor_user_account_id:string;accepted_at:string;disposition:Disposition;text:string|null;source_media:SourceMedia;coverage:'OWNER_ASSERTED_TEXT_ONLY';confirmed_generation:string;accepted_context_version:string;policy_epoch:string;observation_epoch:string;reviewed_ingress_checkpoint:string;reviewed_input_state_hash:string};
export type ContextReason = 'CONTEXT_POLICY_PAUSED'|'CONTEXT_CONFIRMATION_REQUIRED'|'CONTEXT_UNRESOLVED'|'NEW_OBSERVATION'|'CONTEXT_INPUT_UNRESOLVED'|'CONTEXT_COVERAGE_REQUIRED'|'CONTEXT_TOO_LARGE';
export type AutomationWork = {state:'IDLE';reason:null;job_id:null;turn_id:null;observed_at:string}|{state:'WAITING_CONTEXT';reason:'CONTEXT_INPUT_PENDING';job_id:string;turn_id:string;observed_at:string}|{state:'OPERATOR_REQUIRED';reason:ContextReason|'CONTEXT_WAIT_EXHAUSTED';job_id:string;turn_id:string;observed_at:string};
export type HumanContextState = {workspace_id:string;conversation_id:string;client_id:string;observed_at:string;control_mode:'HUMAN'|'AI';control_generation:string;context_version:string;policy:'OFF_UNUSED'|'ON'|'PAUSED';policy_epoch:string;observation_epoch:string;ingress_checkpoint:string;input_state_hash:string;input_gap_limit_exceeded:boolean;has_unsequenced_context_input:boolean;current_revision:Revision|null;review_status:'POLICY_INACTIVE'|'POLICY_PAUSED'|'BOOTSTRAP_REQUIRED'|'CONFIRMATION_REQUIRED'|'UNRESOLVED'|'NEW_OBSERVATION'|'INPUT_UNRESOLVED'|'COVERAGE_REQUIRED'|'INPUT_PENDING'|'CONFIRMED';context_blockers:ContextBlocker[];resume_blockers:(ContextBlocker|'HUMAN_REQUIRED')[];history_truncated:boolean;coverage_status:Coverage;pending_context_input:boolean;has_failed_context_input:boolean;unreviewed_failed_context_input:boolean;automation_work:AutomationWork;manual_delivery:{has_dispatching:boolean;has_unknown:boolean}};
export type Preview = {kind:'TEXT';text:string}|{kind:'PHOTO';caption:string|null;image_availability:'NATIVE_UNAVAILABLE'}|{kind:'UNSUPPORTED';reason:'UNSUPPORTED_CONTENT'|'AMBIGUOUS_ORIGIN'|'UNAVAILABLE_PROJECTION'}|{kind:'DELETE';target_count:number};
export type Observation = {observation_id:string;epoch:string;classification:'NATIVE_CANDIDATE'|'AMBIGUOUS_NONCLIENT'|'CANONICAL_MUTATION'|'UNBOUND_MUTATION';observed_at:string;source_kind:'NEW'|'EDIT'|'DELETE';preview:Preview;coverage:'PROVIDER_OBSERVATION_ONLY'};
export type ObservationPage = {items:Observation[];next_cursor:string|null;through_epoch:string;current_epoch:string;observed_at:string};
export type ReconcileBody = Readonly<{expected_client_id:string;expected_control_generation:string;expected_context_version:string;expected_policy_epoch:string;expected_observation_epoch:string;expected_ingress_checkpoint:string;expected_input_state_hash:string;expected_revision_id:string|null;disposition:Disposition;text:string|null;source_media:SourceMedia;attestation:'REVIEWED_AVAILABLE_CONTEXT'}>;
export type ReconcileReceipt = {outcome:'ACCEPTED'|'REPLAY';result:{workspace_id:string;conversation_id:string;client_id:string;receipt_id:string;revision_id:string;revision_no:string;previous_revision_id:string|null;audit_event_id:string;control_generation:string;previous_context_version:string;accepted_context_version:string;policy_epoch:string;observation_epoch:string;reviewed_ingress_checkpoint:string;reviewed_input_state_hash:string;disposition:Disposition;source_media:SourceMedia;coverage:'OWNER_ASSERTED_TEXT_ONLY';accepted_at:string}};
export class HumanContextError extends Error {constructor(public status:number,public code:string){super(code);}}
const invalid=():never=>{throw new HumanContextError(502,'INVALID_RESPONSE');};
const object=(v:unknown,keys:string[]):Record<string,unknown>=>{if(typeof v!=='object'||v===null||Array.isArray(v)||Object.keys(v).length!==keys.length||!keys.every(k=>Object.hasOwn(v,k)))return invalid();return v as Record<string,unknown>;};
const match=(v:unknown,re:RegExp):v is string=>typeof v==='string'&&re.test(v);
const uuid=(v:unknown)=>match(v,/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/);
const decimal=(v:unknown,zero=false)=>match(v,zero?/^(0|[1-9][0-9]{0,18})$(?![\s\S])/:/^[1-9][0-9]{0,18}$(?![\s\S])/) && BigInt(v)<=9223372036854775807n;
const digest=(v:unknown)=>match(v,/^[0-9a-f]{64}$(?![\s\S])/);
const oneOf=(v:unknown,values:readonly string[])=>typeof v==='string'&&values.includes(v);
const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
const timestamp=(v:unknown)=>{if(!match(v,/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$(?![\s\S])/)||v.startsWith('0000'))return false;const d=new Date(v);return !Number.isNaN(d.valueOf())&&d.toISOString()===v.slice(0,23)+'Z';};
const coverage=['UNCONFIRMED','UNRESOLVED','OWNER_TEXT','CANONICAL_COMPLETE','CANONICAL_TRUNCATED'];
const reasons=['CONTEXT_POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_UNRESOLVED','NEW_OBSERVATION','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED','CONTEXT_TOO_LARGE'];
function scalar(v:unknown,min:number,nonblank=false):v is string{return typeof v==='string'&&[...v].length>=min&&[...v].length<=4096&&!/[\u0000\uD800-\uDFFF]/u.test(v)&&new TextEncoder().encode(v).length<=16384&&(!nonblank||!/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(v));}
function content(v:Record<string,unknown>){if(!oneOf(v.disposition,['OWNER_TEXT','CANONICAL_SUFFICIENT','UNRESOLVED'])||!oneOf(v.source_media,['NONE','UNAVAILABLE'])||!(v.text===null||scalar(v.text,1,true))||(v.disposition==='OWNER_TEXT'&&v.text===null)||(v.disposition==='CANONICAL_SUFFICIENT'&&(v.text!==null||v.source_media!=='NONE')))invalid();}
function identity(v:Record<string,unknown>,c:ControlContext){if(!uuid(v.workspace_id)||!uuid(v.conversation_id)||!uuid(v.client_id)||v.workspace_id!==c.workspace||v.conversation_id!==c.conversation||v.client_id!==c.client)invalid();}
function revision(value:unknown):Revision{
  const v=object(value,['revision_id','revision_no','previous_revision_id','actor_user_account_id','accepted_at','disposition','text','source_media','coverage','confirmed_generation','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_checkpoint','reviewed_input_state_hash']);
  content(v);
  if(!uuid(v.revision_id)||!uuid(v.actor_user_account_id)||!decimal(v.revision_no)||!(v.previous_revision_id===null||uuid(v.previous_revision_id))||!timestamp(v.accepted_at)||v.coverage!=='OWNER_ASSERTED_TEXT_ONLY'||!['confirmed_generation','accepted_context_version','policy_epoch'].every(k=>decimal(v[k]))||!['observation_epoch','reviewed_ingress_checkpoint'].every(k=>decimal(v[k],true))||!digest(v.reviewed_input_state_hash)||(v.previous_revision_id===null)!==(v.revision_no==='1')||v.previous_revision_id===v.revision_id)invalid();
  return v as unknown as Revision;
}
export function parseContextHold(value:unknown):ContextHold{
  const v=object(value,['reason','policy','policy_epoch','observation_epoch','coverage_status']);
  if(!oneOf(v.reason,[...reasons.filter(r=>r!=='CONTEXT_TOO_LARGE'),'CONTEXT_INPUT_PENDING'])||!oneOf(v.policy,['ON','PAUSED'])||!decimal(v.policy_epoch)||!decimal(v.observation_epoch,true)||!oneOf(v.coverage_status,coverage))invalid();
  return v as unknown as ContextHold;
}
export function parseHumanContext(value:unknown,c:ControlContext):HumanContextState{
  const v=object(value,['workspace_id','conversation_id','client_id','observed_at','control_mode','control_generation','context_version','policy','policy_epoch','observation_epoch','ingress_checkpoint','input_state_hash','input_gap_limit_exceeded','has_unsequenced_context_input','current_revision','review_status','context_blockers','resume_blockers','history_truncated','coverage_status','pending_context_input','has_failed_context_input','unreviewed_failed_context_input','automation_work','manual_delivery']);identity(v,c);
  if(!timestamp(v.observed_at)||!oneOf(v.control_mode,['HUMAN','AI'])||!decimal(v.control_generation)||!decimal(v.context_version)||!oneOf(v.policy,['OFF_UNUSED','ON','PAUSED'])||!['policy_epoch','observation_epoch','ingress_checkpoint'].every(k=>decimal(v[k],true))||!digest(v.input_state_hash)||!['input_gap_limit_exceeded','has_unsequenced_context_input','history_truncated','pending_context_input','has_failed_context_input','unreviewed_failed_context_input'].every(k=>typeof v[k]==='boolean'))invalid();
  const delivery=object(v.manual_delivery,['has_dispatching','has_unknown']);if(typeof delivery.has_dispatching!=='boolean'||typeof delivery.has_unknown!=='boolean')invalid();
  const r=v.current_revision===null?null:revision(v.current_revision),work=object(v.automation_work,['state','reason','job_id','turn_id','observed_at']);
  if(!timestamp(work.observed_at)||work.observed_at!==v.observed_at)invalid();
  if(work.state==='IDLE'){if(work.reason!==null||work.job_id!==null||work.turn_id!==null)invalid();}
  else if(!uuid(work.job_id)||!uuid(work.turn_id)||!(work.state==='WAITING_CONTEXT'&&work.reason==='CONTEXT_INPUT_PENDING')&&!(work.state==='OPERATOR_REQUIRED'&&oneOf(work.reason,[...reasons,'CONTEXT_WAIT_EXHAUSTED'])))invalid();
  const rawBlockers=v.context_blockers;if(!Array.isArray(rawBlockers)||!same(rawBlockers,blockerOrder.filter(b=>rawBlockers.includes(b))))invalid();
  const blockers=v.context_blockers as ContextBlocker[];
  const statuses=['POLICY_INACTIVE','POLICY_PAUSED','BOOTSTRAP_REQUIRED','CONFIRMATION_REQUIRED','UNRESOLVED','NEW_OBSERVATION','INPUT_UNRESOLVED','COVERAGE_REQUIRED','INPUT_PENDING'];
  if(v.review_status!==(blockers.length?statuses[blockerOrder.indexOf(blockers[0])]:'CONFIRMED'))invalid();
  const expectedCoverage=r===null?'UNCONFIRMED':r.disposition==='UNRESOLVED'?'UNRESOLVED':r.disposition==='OWNER_TEXT'?'OWNER_TEXT':v.history_truncated?'CANONICAL_TRUNCATED':'CANONICAL_COMPLETE';
  if(v.coverage_status!==expectedCoverage||(v.unreviewed_failed_context_input&&!v.has_failed_context_input))invalid();
  const expected:string[]=[...blockers];
  if(v.policy==='OFF_UNUSED'){if(v.policy_epoch!=='0'||v.observation_epoch!=='0'||r!==null||!same(blockers,['POLICY_INACTIVE']))invalid();expected.length=0;}
  else {if(v.policy_epoch==='0'||blockers.includes('POLICY_INACTIVE')||blockers.includes('POLICY_PAUSED')!==(v.policy==='PAUSED')||blockers.includes('CONTEXT_CONFIRMATION_REQUIRED')!==(r===null)||blockers.includes('CONTEXT_INPUT_PENDING')!==v.pending_context_input)invalid();if(v.control_mode==='AI')expected.splice(v.policy==='PAUSED'?1:0,0,'HUMAN_REQUIRED');}
  if(!same(v.resume_blockers,expected))invalid();
  return v as unknown as HumanContextState;
}
type Cursor={v:1;ws:string;C:string;Client:string;P:string;through_N:string;after_N:string};
export function parseObservationCursor(token:string,c:ControlContext):Cursor{
  try{
    if(!match(token,/^[A-Za-z0-9_-]{1,1024}$(?![\s\S])/))return invalid();
    const bytes=Uint8Array.from(atob(token.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-token.length%4)%4)),c=>c.charCodeAt(0));
    const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes),parsed=JSON.parse(raw),v=object(parsed,['v','ws','C','Client','P','through_N','after_N']);
    if(Object.keys(v).join(',')!=='v,ws,C,Client,P,through_N,after_N'||JSON.stringify(v)!==raw||v.v!==1||!uuid(v.ws)||!uuid(v.C)||!uuid(v.Client)||v.ws!==c.workspace||v.C!==c.conversation||v.Client!==c.client||!['P','through_N','after_N'].every(k=>decimal(v[k],true))||BigInt(v.after_N as string)>BigInt(v.through_N as string))return invalid();
    if(btoa(String.fromCharCode(...new TextEncoder().encode(raw))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')!==token)return invalid();
    return v as unknown as Cursor;
  }catch{return invalid();}
}
export function parseObservations(value:unknown,c:ControlContext,cursor:string|null=null,limit=20):ObservationPage{
  if(!Number.isInteger(limit)||limit<1||limit>100)invalid();const old=cursor===null?null:parseObservationCursor(cursor,c);
  const v=object(value,['items','next_cursor','through_epoch','current_epoch','observed_at']);
  if(!Array.isArray(v.items)||v.items.length>limit||!decimal(v.through_epoch,true)||!decimal(v.current_epoch,true)||BigInt(v.through_epoch as string)>BigInt(v.current_epoch as string)||!timestamp(v.observed_at)||!(v.next_cursor===null||typeof v.next_cursor==='string')||(old&&old.through_N!==v.through_epoch)||(!old&&v.through_epoch!==v.current_epoch))invalid();
  let previous=old?.after_N??'0';
  for(const item of v.items as unknown[]){
    const row=object(item,['observation_id','epoch','classification','observed_at','source_kind','preview','coverage']);
    if(!uuid(row.observation_id)||!decimal(row.epoch)||BigInt(row.epoch as string)<=BigInt(previous)||BigInt(row.epoch as string)>BigInt(v.through_epoch as string)||!oneOf(row.classification,['NATIVE_CANDIDATE','AMBIGUOUS_NONCLIENT','CANONICAL_MUTATION','UNBOUND_MUTATION'])||!timestamp(row.observed_at)||!oneOf(row.source_kind,['NEW','EDIT','DELETE'])||row.coverage!=='PROVIDER_OBSERVATION_ONLY')invalid();previous=row.epoch as string;
    if(typeof row.preview!=='object'||row.preview===null||!('kind' in row.preview))invalid();
    const kind=(row.preview as {kind:unknown}).kind;
    const p=object(row.preview,kind==='TEXT'?['kind','text']:kind==='PHOTO'?['kind','caption','image_availability']:kind==='DELETE'?['kind','target_count']:['kind','reason']);
    if((row.source_kind==='DELETE')!==(kind==='DELETE'))invalid();
    if(kind==='TEXT'){if(!scalar(p.text,1))invalid();}
    else if(kind==='PHOTO'){if(!(p.caption===null||scalar(p.caption,0))||p.image_availability!=='NATIVE_UNAVAILABLE')invalid();}
    else if(kind==='DELETE'){if(typeof p.target_count!=='number'||!Number.isInteger(p.target_count)||p.target_count<1||p.target_count>100)invalid();}
    else if(kind!=='UNSUPPORTED'||!oneOf(p.reason,['UNSUPPORTED_CONTENT','AMBIGUOUS_ORIGIN','UNAVAILABLE_PROJECTION']))invalid();
  }
  if(v.next_cursor!==null){const next=parseObservationCursor(v.next_cursor as string,c);if(!(v.items as unknown[]).length||next.through_N!==v.through_epoch||next.after_N!==previous||(old&&next.P!==old.P))invalid();}
  return v as unknown as ObservationPage;
}
export function serializeReconcile(body:ReconcileBody):string{
  try{
    const v=object(body,['expected_client_id','expected_control_generation','expected_context_version','expected_policy_epoch','expected_observation_epoch','expected_ingress_checkpoint','expected_input_state_hash','expected_revision_id','disposition','text','source_media','attestation']);content(v);
    if(!uuid(v.expected_client_id)||!decimal(v.expected_control_generation)||!decimal(v.expected_context_version)||!['expected_policy_epoch','expected_observation_epoch','expected_ingress_checkpoint'].every(k=>decimal(v[k],true))||!digest(v.expected_input_state_hash)||!(v.expected_revision_id===null||uuid(v.expected_revision_id))||v.attestation!=='REVIEWED_AVAILABLE_CONTEXT')invalid();
  }catch{throw new HumanContextError(422,'INVALID_REQUEST');}
  const encoded=JSON.stringify(body);if(new TextEncoder().encode(encoded).length>4096)throw new HumanContextError(413,'BODY_TOO_LARGE');return encoded;
}
export function reconcileBody(s:HumanContextState,disposition:Disposition,text:string|null,source_media:SourceMedia):ReconcileBody{return Object.freeze({expected_client_id:s.client_id,expected_control_generation:s.control_generation,expected_context_version:s.context_version,expected_policy_epoch:s.policy_epoch,expected_observation_epoch:s.observation_epoch,expected_ingress_checkpoint:s.ingress_checkpoint,expected_input_state_hash:s.input_state_hash,expected_revision_id:s.current_revision?.revision_id??null,disposition,text,source_media,attestation:'REVIEWED_AVAILABLE_CONTEXT'});}
export function parseReconcileReceipt(value:unknown,c:ControlContext,body:ReconcileBody):ReconcileReceipt{
  const v=object(value,['outcome','result']),r=object(v.result,['workspace_id','conversation_id','client_id','receipt_id','revision_id','revision_no','previous_revision_id','audit_event_id','control_generation','previous_context_version','accepted_context_version','policy_epoch','observation_epoch','reviewed_ingress_checkpoint','reviewed_input_state_hash','disposition','source_media','coverage','accepted_at']);identity(r,c);
  if(!oneOf(v.outcome,['ACCEPTED','REPLAY'])||!['receipt_id','revision_id','audit_event_id'].every(k=>uuid(r[k]))||r.receipt_id!==r.revision_id||!['revision_no','control_generation','previous_context_version','accepted_context_version','policy_epoch'].every(k=>decimal(r[k]))||!['observation_epoch','reviewed_ingress_checkpoint'].every(k=>decimal(r[k],true))||!digest(r.reviewed_input_state_hash)||!timestamp(r.accepted_at)||r.coverage!=='OWNER_ASSERTED_TEXT_ONLY'||!(r.previous_revision_id===null||uuid(r.previous_revision_id))||(r.previous_revision_id===null)!==(r.revision_no==='1')||BigInt(r.accepted_context_version as string)!==BigInt(r.previous_context_version as string)+1n)invalid();
  for(const [result,expected] of [['client_id','expected_client_id'],['control_generation','expected_control_generation'],['previous_context_version','expected_context_version'],['policy_epoch','expected_policy_epoch'],['observation_epoch','expected_observation_epoch'],['reviewed_ingress_checkpoint','expected_ingress_checkpoint'],['reviewed_input_state_hash','expected_input_state_hash'],['previous_revision_id','expected_revision_id'],['disposition','disposition'],['source_media','source_media']] as const)if(r[result]!==body[expected])invalid();
  return v as unknown as ReconcileReceipt;
}
export function parseHumanContextError(value:unknown,status:number):HumanContextError{
  const v=object(value,['error']),e=object(v.error,['code']);
  const codes:Record<number,string[]>={401:['SESSION_REQUIRED'],403:['ORIGIN_DENIED','CSRF_REJECTED','ACCESS_DENIED'],404:['NOT_FOUND'],409:['IDEMPOTENCY_KEY_CONFLICT','STALE_STATE','VERSION_EXHAUSTED','CONTEXT_POLICY_INACTIVE','CONTEXT_POLICY_PAUSED','HUMAN_REQUIRED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_UNRESOLVED','CONTEXT_INPUT_PENDING','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED','CONTEXT_CURSOR_STALE'],413:['BODY_TOO_LARGE'],415:['UNSUPPORTED_MEDIA_TYPE'],422:['INVALID_REQUEST'],429:['RATE_LIMITED'],500:['INTERNAL_ERROR'],503:['UNAVAILABLE']};
  if(!oneOf(e.code,codes[status]??[]))invalid();return new HumanContextError(status,e.code as string);
}
async function request<T>(c:ControlContext,route:string,parse:(v:unknown)=>T,init:RequestInit,signal?:AbortSignal):Promise<T>{const controller=new AbortController(),abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();const timer=setTimeout(abort,10000);try{const r=await fetch(`/api/v1/workspaces/${encodeURIComponent(c.workspace)}/conversations/${encodeURIComponent(c.conversation)}/human-context${route}`,{...init,credentials:'include',cache:'no-store',signal:controller.signal});let value:unknown;try{value=await r.json();}catch{return invalid();}if(r.status!==200)throw parseHumanContextError(value,r.status);return parse(value);}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}}
export const humanContextApi={read:(c:ControlContext,signal?:AbortSignal)=>request(c,'',v=>parseHumanContext(v,c),{},signal),observations:(c:ControlContext,cursor:string|null=null,signal?:AbortSignal)=>request(c,`/observations?limit=20${cursor===null?'':`&cursor=${encodeURIComponent(cursor)}`}`,v=>parseObservations(v,c,cursor),{},signal),reconcile:(c:ControlContext,body:ReconcileBody,key:string,csrf:string,signal?:AbortSignal)=>{const encoded=serializeReconcile(body);if(body.expected_client_id!==c.client||!match(key,/^[A-Za-z0-9._:-]{1,128}$(?![\s\S])/))throw new HumanContextError(422,'INVALID_REQUEST');return request(c,'/reconcile',v=>parseReconcileReceipt(v,c,body),{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key},body:encoded},signal);}};
