import {parseDurationPolicy,type DurationPolicy} from './configuration-api';

export type IntakeScope = { workspace: string; business: string; conversation?: string; client?: string };
export type Source = { message_id: string; source_version: string; quote: string; analysis_id: string|null; analysis_sha256: string|null };
export type FieldId = (typeof fields)[number];
export type Fact = { field: FieldId; value: string; status: 'client-stated'|'observed'|'owner-confirmed'; source: Source; confirmed_by: string|null; conflict: boolean };
export type Intake = { revision: 'preliminary_intake_v1'; workspace_id: string; business_id: string; conversation_id: string; client_id: string; service_id: string|null; release_id: string|null; activation_version: string; template_revision: 'tattoo_intake_v1'|null; control_generation: string; context_version: string; version: string; category: string; facts: Fact[]; missing: string[]; conflicts: string[]; status: 'NOT_STARTED'|'CLARIFY'|'OWNER_HANDOFF'|'PRELIMINARILY_COMPLETE'; question: string|null; sources: {message_id:string;source_version:string;text:string}[]; fingerprint: string; preliminary: true };
type IntentSource = Pick<Source, 'message_id'|'source_version'>;
export type DraftCommand = {
 expected_version: string;
 expected_fingerprint: string;
 intent_source: IntentSource;
 fields: FieldId[];
 selection: 'ONE_WORK'|'UNCLEAR';
};
export type DraftRevisionCommand = {
 expected_revision: string;
 expected_version: string;
 expected_fingerprint: string;
 field?: FieldId;
 source: IntentSource;
 selection: 'ONE_WORK'|'UNCLEAR';
};
export type DraftListItem = {
 request_id: string;
 revision: string;
 service_name: string;
 intent_source: IntentSource;
 idea: string|null;
};
export type ServiceRequestDraft = {
 request_id: string;
 workspace_id: string;
 business_id: string;
 conversation_id: string;
 client_id: string;
 service_id: string;
 service_name: string;
 release_id: string;
 template_revision: 'tattoo_intake_v1';
 revision: string;
 state: 'DRAFT';
 intent_source: IntentSource;
 facts: Fact[];
 missing: FieldId[];
 conflicts: FieldId[];
 question: string|null;
};
const assessmentOutcomes=['FEASIBLE','NEEDS_DATA','NEEDS_OWNER','DECLINED'] as const;
const assessmentReasons=['FIXED_DURATION','SIZE_DURATION_RULE','MISSING_FACT','CONFLICTING_FACT','SOURCE_CHANGED',
 'SIZE_NEEDS_CONFIRMATION','MIN_AGE_UNCONFIRMED','SIZE_LIMIT_EXCEEDED','OWNER_HANDOFF','OWNER_DURATION',
 'SERVICE_UNAVAILABLE','DURATION_UNPUBLISHED'] as const;
export type ServiceAssessment = {
 assessment_id:string;
 request_id:string;
 request_revision:string;
 release_id:string|null;
 activation_version:string;
 current:boolean;
 outcome:(typeof assessmentOutcomes)[number];
 reason:(typeof assessmentReasons)[number];
 field:FieldId|null;
 rule_id:string|null;
 limit:number|null;
 size_mm:number|null;
 occupied_minutes:number|null;
 duration_policy:DurationPolicy|null;
 evidence:Fact[];
 complex_work?:{category:'COVER_UP'|'OTHER_COMPLEX';source:IntentSource;source_current:boolean};
 archived_duration?:{assessment_id:string;request_revision:string;release_id:string|null;activation_version:string;occupied_minutes:number};
};
export type CaseInput = { description: string; asset: {asset_id:string;asset_version_id:string}|null; width_mm:number|null; height_mm:number|null; placement:string|null; style:string|null; detail:string|null; fill:string|null; provider:string|null; working_minutes:number|null; occupied_minutes:number|null; setup_minutes:number|null; stencil_minutes:number|null; break_minutes:number|null; cleanup_minutes:number|null; treatment:'INCLUDED'|'EXCLUDED'|'UNKNOWN'; session_count:number|null; session_minutes:number[]|null; explanation:string|null };
export type DurationCase = {case_id:string;version:string;state:'DRAFT'|'CONFIRMED'|'REVOKED';data:CaseInput;confirmed_by:string|null;source_current:boolean};
export type CasePage = {workspace_id:string;business_id:string;items:DurationCase[]};
export type CaseMatch = {case:DurationCase;matches:string[];differences:string[];unknown:string[]};
export type CaseSearch = {workspace_id:string;business_id:string;items:CaseMatch[]};
export type Receipt = {outcome:'ACCEPTED'|'REPLAY';receipt_id:string;version:string};
export class IntakeError extends Error {constructor(public status:number,public code:string){super(code);}}
const invalid=():never=>{throw new IntakeError(502,'INVALID_RESPONSE');};
export const fields=['idea','placement','approximate_size','style','references'] as const;
export const labels:Record<string,string>={idea:'Идея',placement:'Место',approximate_size:'Примерный размер',style:'Стиль',references:'Референсы'};
const uuid=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\s\S])/.test(v);
const digest=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{64}$(?![\s\S])/.test(v);
const decimal=(v:unknown,zero=true)=>typeof v==='string'&&/^(0|[1-9][0-9]{0,18})$(?![\s\S])/.test(v)&&BigInt(v)<=9223372036854775807n&&(zero||v!=='0');
const text=(v:unknown,max:number)=>typeof v==='string'&&[...v].length<=max&&!/[\u0000\uD800-\uDFFF]/u.test(v);
const one=(v:unknown,choices:readonly string[])=>typeof v==='string'&&choices.includes(v);
const nullable=(v:unknown,check:(v:unknown)=>boolean)=>v===null||check(v);
const positiveWithin=(v:unknown,max:number)=>typeof v==='number'&&Number.isInteger(v)&&v>=1&&v<=max;
const serviceId=(v:unknown)=>typeof v==='string'&&/^[a-z][a-z0-9_-]{0,39}$/.test(v);
function object(v:unknown,keys:string[]):Record<string,unknown>{if(typeof v!=='object'||v===null||Array.isArray(v)||Object.keys(v).length!==keys.length||!keys.every(k=>Object.hasOwn(v,k)))return invalid();return v as Record<string,unknown>;}
function array(v:unknown,max:number):unknown[]{if(!Array.isArray(v)||v.length>max)return invalid();return v;}
function inConversation(v:Record<string,unknown>,scope:IntakeScope){
 return v.workspace_id===scope.workspace&&v.business_id===scope.business&&v.conversation_id===scope.conversation
  &&(scope.client===undefined||v.client_id===scope.client)
  &&['workspace_id','business_id','conversation_id','client_id'].every(k=>uuid(v[k]));
}
function parseFacts(value:unknown):Fact[]{
 const facts=array(value,5).map(raw=>{
  const f=object(raw,['field','value','status','source','confirmed_by','conflict']);
  if(!one(f.field,fields)||!text(f.value,300)||!(f.value as string).trim()||!one(f.status,['client-stated','observed','owner-confirmed'])
    ||!nullable(f.confirmed_by,uuid)||typeof f.conflict!=='boolean'||(f.status==='owner-confirmed')!==(f.confirmed_by!==null))invalid();
  const source=object(f.source,['message_id','source_version','quote','analysis_id','analysis_sha256']);
  if(!uuid(source.message_id)||!digest(source.source_version)||!text(source.quote,500)||!nullable(source.analysis_id,uuid)
    ||!nullable(source.analysis_sha256,digest)||(source.analysis_id===null)!==(source.analysis_sha256===null))invalid();
  return f as Fact;
 });
 if(new Set(facts.map(f=>f.field)).size!==facts.length)invalid();
 return facts;
}
function checkIntentSource(value:unknown){
 const source=object(value,['message_id','source_version']);
 if(!uuid(source.message_id)||!digest(source.source_version))invalid();
}
function parseDraftList(value:unknown):DraftListItem[]{
 const {items}=object(value,['items']);
 if(!Array.isArray(items))return invalid();
 const cards=items.map(raw=>{
  const card=object(raw,['request_id','revision','service_name','intent_source','idea']);
  if(!uuid(card.request_id)||!decimal(card.revision,false)||!text(card.service_name,100)||!(card.service_name as string).trim()
    ||!nullable(card.idea,x=>text(x,300)&&!!(x as string).trim()))invalid();
  checkIntentSource(card.intent_source);
  return card as DraftListItem;
 });
 if(new Set(cards.map(card=>card.request_id)).size!==cards.length)invalid();
 return cards;
}
export function parseDraft(value:unknown,scope:IntakeScope,requestId?:string):ServiceRequestDraft{
 const v=object(value,['request_id','workspace_id','business_id','conversation_id','client_id','service_id','service_name','release_id',
  'template_revision','revision','state','intent_source','facts','missing','conflicts','question']);
 if(!inConversation(v,scope)||!uuid(v.request_id)||(requestId!==undefined&&v.request_id!==requestId)
   ||!uuid(v.release_id)||!serviceId(v.service_id)||!text(v.service_name,100)||!(v.service_name as string).trim()
   ||v.template_revision!=='tattoo_intake_v1'||!decimal(v.revision,false)||v.state!=='DRAFT'||!nullable(v.question,x=>text(x,300)))invalid();
 checkIntentSource(v.intent_source);
 const facts=parseFacts(v.facts);
 if(facts.some(f=>f.source.quote!==''||(f.status==='observed'&&f.source.analysis_id===null)))invalid();
 for(const key of ['missing','conflicts']){
  const entries=array(v[key],5);
  if(!entries.every(f=>one(f,fields))||new Set(entries).size!==entries.length)invalid();
 }
 return v as ServiceRequestDraft;
}
export function parseAssessment(value:unknown,requestId:string,expectedRevision?:string):ServiceAssessment{
 const optional=['complex_work','archived_duration'].filter(key=>typeof value==='object'&&value!==null&&Object.hasOwn(value,key));
 const v=object(value,['assessment_id','request_id','request_revision','release_id','activation_version','current','outcome','reason',
  'field','rule_id','limit','size_mm','occupied_minutes','duration_policy','evidence',...optional]);
 if(!uuid(v.assessment_id)||!uuid(v.request_id)||v.request_id!==requestId||!decimal(v.request_revision,false)
   ||(expectedRevision!==undefined&&v.request_revision!==expectedRevision)||!nullable(v.release_id,uuid)||!decimal(v.activation_version)
   ||typeof v.current!=='boolean'||!one(v.outcome,assessmentOutcomes)||!one(v.reason,assessmentReasons)
   ||!nullable(v.field,x=>one(x,fields))||!nullable(v.rule_id,serviceId)||!nullable(v.limit,x=>positiveWithin(x,1000))
   ||!nullable(v.size_mm,x=>positiveWithin(x,1000))||!nullable(v.occupied_minutes,x=>positiveWithin(x,10080))
   ||(v.outcome==='FEASIBLE')!==(v.occupied_minutes!==null))invalid();
 const facts=parseFacts(v.evidence);
 if(facts.some(fact=>fact.source.quote!==''||(fact.status==='observed'&&fact.source.analysis_id===null)))invalid();
 if(v.duration_policy!==null){
  try{parseDurationPolicy(v.duration_policy);}catch{return invalid();}
 }
 if(v.complex_work!==undefined){
  const work=object(v.complex_work,['category','source','source_current']);
  if(!one(work.category,['COVER_UP','OTHER_COMPLEX'])||typeof work.source_current!=='boolean'
    ||v.outcome!=='NEEDS_OWNER'||v.duration_policy!==null)invalid();
  checkIntentSource(work.source);
 }
 if(v.archived_duration!==undefined){
  const archive=object(v.archived_duration,['assessment_id','request_revision','release_id','activation_version','occupied_minutes']);
  if(!uuid(archive.assessment_id)||archive.assessment_id===v.assessment_id
    ||!decimal(archive.request_revision,false)||BigInt(archive.request_revision as string)>BigInt(v.request_revision as string)
    ||!nullable(archive.release_id,uuid)||!decimal(archive.activation_version)||!positiveWithin(archive.occupied_minutes,10080))invalid();
 }
 return v as ServiceAssessment;
}
export function parseIntake(value:unknown,scope:IntakeScope):Intake{
 const v=object(value,['revision','workspace_id','business_id','conversation_id','client_id','service_id','release_id','activation_version','template_revision','control_generation','context_version','version','category','facts','missing','conflicts','status','question','sources','fingerprint','preliminary']);
 if(v.revision!=='preliminary_intake_v1'||v.preliminary!==true||!inConversation(v,scope)||!nullable(v.release_id,uuid)||!nullable(v.service_id,serviceId)||!decimal(v.activation_version)||!decimal(v.version)||!decimal(v.control_generation,false)||!decimal(v.context_version,false)||!one(v.category,['NEW_TATTOO','COVER_UP','OTHER_COMPLEX','FAQ_ONLY','AMBIGUOUS'])||!one(v.status,['NOT_STARTED','CLARIFY','OWNER_HANDOFF','PRELIMINARILY_COMPLETE'])||!nullable(v.template_revision,x=>x==='tattoo_intake_v1')||!nullable(v.question,x=>text(x,300))||!digest(v.fingerprint))invalid();
 parseFacts(v.facts);
 for(const k of ['missing','conflicts'])if(!array(v[k],5).every(f=>one(f,fields)))invalid();
 for(const raw of array(v.sources,64)){const s=object(raw,['message_id','source_version','text']);if(!uuid(s.message_id)||!digest(s.source_version)||!text(s.text,4096))invalid();}
 return v as unknown as Intake;
}
function parseCase(value:unknown):DurationCase{
 const v=object(value,['case_id','version','state','data','confirmed_by','source_current']);if(!uuid(v.case_id)||!decimal(v.version,false)||!one(v.state,['DRAFT','CONFIRMED','REVOKED'])||!nullable(v.confirmed_by,uuid)||typeof v.source_current!=='boolean'||(v.state==='CONFIRMED')!==(v.confirmed_by!==null))invalid();
 const d=object(v.data,['description','asset','width_mm','height_mm','placement','style','detail','fill','provider','working_minutes','occupied_minutes','setup_minutes','stencil_minutes','break_minutes','cleanup_minutes','treatment','session_count','session_minutes','explanation']);
 if(!text(d.description,500)||!(d.description as string).trim()||!one(d.treatment,['INCLUDED','EXCLUDED','UNKNOWN']))invalid();
 for(const k of ['placement','style','detail','fill','provider','explanation'])if(!nullable(d[k],x=>text(x,k==='explanation'?500:300)))invalid();
 for(const k of ['width_mm','height_mm','working_minutes','occupied_minutes','setup_minutes','stencil_minutes','break_minutes','cleanup_minutes','session_count'])if(!nullable(d[k],x=>Number.isInteger(x)&&(x as number)>=(['setup_minutes','stencil_minutes','break_minutes','cleanup_minutes'].includes(k)?0:1)&&(x as number)<=(k==='session_count'?20:['width_mm','height_mm'].includes(k)?3000:100000)))invalid();
 if(d.asset!==null){const a=object(d.asset,['asset_id','asset_version_id']);if(!uuid(a.asset_id)||!uuid(a.asset_version_id))invalid();}
 if(d.session_minutes!==null&&(!array(d.session_minutes,20).every(x=>Number.isInteger(x)&&(x as number)>0&&(x as number)<=100000)||(d.session_minutes as unknown[]).length!==d.session_count))invalid();
 return v as unknown as DurationCase;
}
export function parseCases(value:unknown,scope:IntakeScope):CasePage{const v=object(value,['workspace_id','business_id','items']);if(v.workspace_id!==scope.workspace||v.business_id!==scope.business)invalid();const items=array(v.items,20).map(parseCase);if(new Set(items.map(i=>i.case_id)).size!==items.length)invalid();return {...v,items} as CasePage;}
function parseSearch(value:unknown,scope:IntakeScope):CaseSearch{const v=object(value,['workspace_id','business_id','items']);if(v.workspace_id!==scope.workspace||v.business_id!==scope.business)invalid();const items=array(v.items,5).map(raw=>{const m=object(raw,['case','matches','differences','unknown']);const c=parseCase(m.case);if(c.state!=='CONFIRMED'||!c.source_current)invalid();for(const k of ['matches','differences','unknown'])if(!array(m[k],4).every(x=>one(x,['placement','style','detail','fill'])))invalid();return {...m,case:c} as CaseMatch;});return {...v,items} as CaseSearch;}
function parseReceipt(value:unknown):Receipt{const v=object(value,['outcome','receipt_id','version']);if(!one(v.outcome,['ACCEPTED','REPLAY'])||!uuid(v.receipt_id)||!decimal(v.version,false))invalid();return v as Receipt;}
function parseDraftReceipt(value:unknown,requestId?:string):{request_id:string}{
 const v=object(value,['request_id']);
 if(!uuid(v.request_id)||(requestId!==undefined&&v.request_id!==requestId))return invalid();
 return {request_id:v.request_id};
}
function jsonMutation(method:'POST'|'PATCH',body:unknown,key:string,csrf:string):RequestInit{
 return {method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':key},body:JSON.stringify(body)};
}
async function request<T>(scope:IntakeScope,path:string,parse:(v:unknown)=>T,signal?:AbortSignal,init:RequestInit={}):Promise<T>{
 const controller=new AbortController(),abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();const timer=setTimeout(abort,10000);
 try{const response=await fetch(`/api/v1/workspaces/${encodeURIComponent(scope.workspace)}/businesses/${encodeURIComponent(scope.business)}/intake${path}`,{...init,credentials:'include',cache:'no-store',signal:controller.signal});let value:unknown;try{value=await response.json();}catch{return invalid();}if(response.status!==200){const e=object(object(value,['error']).error,['code']);if(typeof e.code!=='string')invalid();throw new IntakeError(response.status,e.code as string);}return parse(value);}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
const draftPath=(scope:IntakeScope)=>`/conversations/${encodeURIComponent(scope.conversation??'')}/service-requests`;
const assessmentPath=(scope:IntakeScope,id:string)=>`${draftPath(scope)}/${encodeURIComponent(id)}/assessment`;
export const intakeApi={
 summary:(scope:IntakeScope,signal?:AbortSignal)=>request(scope,`/conversations/${encodeURIComponent(scope.conversation??'')}`,v=>parseIntake(v,scope),signal),
 draft:(scope:IntakeScope,requestId?:string,signal?:AbortSignal)=>request(
  scope,draftPath(scope)+(requestId===undefined?'':`?${new URLSearchParams({request_id:requestId})}`),
  v=>v===null&&requestId===undefined?null:parseDraft(v,scope,requestId),signal
 ),
 drafts:(scope:IntakeScope,signal?:AbortSignal)=>request(scope,`${draftPath(scope)}/cards`,parseDraftList,signal),
 saveDraft:(scope:IntakeScope,body:DraftCommand,key:string,csrf:string,signal?:AbortSignal)=>
  request(scope,draftPath(scope),parseDraftReceipt,signal,jsonMutation('POST',body,key,csrf)),
 reviseDraft:(scope:IntakeScope,requestId:string,body:DraftRevisionCommand,key:string,csrf:string,signal?:AbortSignal)=>
  request(scope,`${draftPath(scope)}/${encodeURIComponent(requestId)}`,v=>parseDraftReceipt(v,requestId),signal,jsonMutation('PATCH',body,key,csrf)),
 assessment:(scope:IntakeScope,requestId:string,signal?:AbortSignal)=>
  request(scope,assessmentPath(scope,requestId),v=>v===null?null:parseAssessment(v,requestId),signal),
 assess:(scope:IntakeScope,requestId:string,revision:string,csrf:string,signal?:AbortSignal)=>
  request(scope,assessmentPath(scope,requestId),v=>parseAssessment(v,requestId,revision),signal,{
   method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({expected_revision:revision}),
  }),
 cases:(scope:IntakeScope,signal?:AbortSignal)=>request(scope,'/duration-cases',v=>parseCases(v,scope),signal),
 search:(scope:IntakeScope,query:Record<string,string>,signal?:AbortSignal)=>request(scope,`/duration-cases/search?${new URLSearchParams(query)}`,v=>parseSearch(v,scope),signal),
 command:(scope:IntakeScope,operation:string,body:unknown,key:string,csrf:string,signal?:AbortSignal)=>request(scope,operation.startsWith('case-')?`/duration-cases/${operation.slice(5)}`:`/conversations/${encodeURIComponent(scope.conversation??'')}/${operation}`,parseReceipt,signal,jsonMutation('POST',body,key,csrf)),
};
export function blankCase():CaseInput{return {description:'',asset:null,width_mm:null,height_mm:null,placement:null,style:null,detail:null,fill:null,provider:null,working_minutes:null,occupied_minutes:null,setup_minutes:null,stencil_minutes:null,break_minutes:null,cleanup_minutes:null,treatment:'UNKNOWN',session_count:null,session_minutes:null,explanation:null};}
