import type {Session} from './api';
import type {Intake,CaseInput,DraftListItem,DurationCase,QuoteDelivery,ServiceAssessment,ServiceRequestDraft} from './intake-api';
import {blankCase} from './intake-api';
export const w='018f0000-0000-7000-8000-000000000001',b='018f0000-0000-7000-8000-000000000002',c='018f0000-0000-7000-8000-000000000003',client='018f0000-0000-7000-8000-000000000004',actor='018f0000-0000-7000-8000-000000000005',message='018f0000-0000-7000-8000-000000000006';
export const scope={workspace:w,business:b,conversation:c,client};
export function session():Session{return {user_account_id:actor,csrf_token:'synthetic-csrf',expires_at:'2026-11-17T00:00:00Z',memberships:[{workspace_id:w,role:'OWNER',permissions:[]}]};}
export function intake():Intake{return {revision:'preliminary_intake_v1',workspace_id:w,business_id:b,conversation_id:c,client_id:client,service_id:'tattoo',release_id:'018f0000-0000-7000-8000-000000000007',activation_version:'1',template_revision:'tattoo_intake_v1',control_generation:'2',context_version:'3',version:'1',category:'NEW_TATTOO',facts:[{field:'idea',value:'flower',status:'client-stated',source:{message_id:message,source_version:'a'.repeat(64),quote:'flower',analysis_id:null,analysis_sha256:null},confirmed_by:null,conflict:false}],missing:['placement','approximate_size','style'],conflicts:[],status:'CLARIFY',question:'На каком месте тела вы хотите татуировку?',sources:[{message_id:message,source_version:'a'.repeat(64),text:'flower'}],fingerprint:'b'.repeat(64),preliminary:true};}
export function example(data:Partial<CaseInput>={}):DurationCase{return {case_id:'018f0000-0000-7000-8000-000000000008',version:'1',state:'DRAFT',data:{...blankCase(),description:'Private owner flower',...data},confirmed_by:null,source_current:true};}
export function draft():ServiceRequestDraft{
 const value=intake(),fact=value.facts[0];
 return {
  request_id:'018f0000-0000-7000-8000-000000000009',workspace_id:w,business_id:b,conversation_id:c,client_id:client,
  service_id:'tattoo',service_name:'Synthetic tattoo consultation',release_id:value.release_id!,
  template_revision:'tattoo_intake_v1',revision:'1',state:'DRAFT',
  intent_source:{message_id:message,source_version:fact.source.source_version},
  facts:[{...fact,source:{...fact.source,quote:''}}],missing:['placement','approximate_size','style'],
  conflicts:[],question:value.question,
 };
}
export function listItem({request_id,revision,service_name,intent_source,facts}:ServiceRequestDraft):DraftListItem{
 return {request_id,revision,service_name,intent_source,idea:facts.find(fact=>fact.field==='idea')?.value??null};
}
export function assessment():ServiceAssessment{
 const value=draft();
 return {
  assessment_id:'018f0000-0000-7000-8000-000000000014',request_id:value.request_id,
  request_revision:value.revision,release_id:value.release_id,activation_version:'1',current:true,
  outcome:'FEASIBLE',reason:'FIXED_DURATION',field:null,rule_id:null,limit:null,size_mm:null,
  occupied_minutes:65,duration_policy:{mode:'FIXED',minutes:65,rule_note:null},evidence:value.facts,
 };
}
export function lateSize():Intake{
 const value=intake(),message_id='018f0000-0000-7000-8000-000000000010',source_version='e'.repeat(64);
 const size={...value.facts[0],field:'approximate_size' as const,value:'12 cm',source:{
  message_id,source_version,quote:'12 cm',analysis_id:null,analysis_sha256:null,
 }};
 return {...value,version:'3',fingerprint:'d'.repeat(64),facts:[size],sources:[
  ...value.sources,{message_id,source_version,text:'For the first flower, the size is 12 cm.'},
 ]};
}

export function quoteDelivery(card=draft(),status:QuoteDelivery['status']='SENT',reason:string|null=null){
 const assessment_id=assessment().assessment_id,price_calculation_id='018f0000-0000-7000-8000-000000000015';
 return {
  status,reason,quote:{
   quote_id:'018f0000-0000-7000-8000-000000000016',version:'1',code:'Q-012ABCD234',terms_sha256:'a'.repeat(64),
   created_at:'2026-11-21T12:00:00.000000Z',expires_at:'2026-11-22T12:00:00.000000Z',
   text:'Цена — 3\u202f500 ₽.\nДлительность следующего сеанса — 65 мин.\nПринимаю Q-012ABCD234',material:{
    workspace_id:card.workspace_id,business_id:card.business_id,conversation_id:card.conversation_id,client_id:card.client_id,
    request_id:card.request_id,request_revision:card.revision,service_id:card.service_id,service_name:card.service_name,
    facts:card.facts,intent_source:card.intent_source,complex_work:null,release_id:card.release_id,activation_version:'1',
    assessment_id,assessment_reason:'FIXED_DURATION',price_calculation_id,price_reason:'FIXED_PRICE',approval_id:null,
    decision_id:null,price_reference_id:price_calculation_id,duration_reference_id:assessment_id,currency:'RUB' as const,
    amount_minor:350000,price_range:null,occupied_minutes:65,deposit_terms_version:card.release_id,
    deposit:{mode:'NONE',amount_minor:null,percent:null},conditions:[],
   },
  },
 };
}
