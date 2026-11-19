import type {Session} from './api';
import type {Intake,CaseInput,DraftListItem,DurationCase,ServiceRequestDraft} from './intake-api';
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
export function lateSize():Intake{
 const value=intake(),message_id='018f0000-0000-7000-8000-000000000010',source_version='e'.repeat(64);
 const size={...value.facts[0],field:'approximate_size' as const,value:'12 cm',source:{
  message_id,source_version,quote:'12 cm',analysis_id:null,analysis_sha256:null,
 }};
 return {...value,version:'3',fingerprint:'d'.repeat(64),facts:[size],sources:[
  ...value.sources,{message_id,source_version,text:'For the first flower, the size is 12 cm.'},
 ]};
}
