import { Session } from './api';
import { EscalationBody, EscalationContext, EscalationOperation, EscalationPage, EscalationReceipt, EscalationView } from './escalation-api';
export const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
export const workspace=id(1),actor=id(2),observed='2030-01-01T00:01:00.123456Z';
export const session=(csrf='csrf'):Session=>({user_account_id:actor,csrf_token:csrf,expires_at:'2030-01-02T00:00:00Z',memberships:[{workspace_id:workspace,role:'OWNER',permissions:['tenancy:read']}]});
export const escalation=(n=10):EscalationView=>({
  workspace_id:workspace,escalation_id:id(n),conversation_id:id(n+100),client_id:id(n+200),turn_id:id(n+300),assignee_user_account_id:actor,
  reason:'OWNER_DECISION_REQUIRED',question:'CONTROLLED ESCALATION TEST: требуется решение владельца.',policy:'LOCAL_TEST_OWNER_WAIT_V1',version:'1',status:'PENDING',
  bound_context:{turn_revision:'9007199254740993',control_generation:'9007199254740995',context_version:'9007199254740997',fingerprint:'a'.repeat(64)},
  current_context:{control_mode:'AI',control_generation:'9007199254740995',context_version:'9007199254740997'},validity:'CURRENT',waiting:'WAITING_FOR_HUMAN',
  created_at:'2030-01-01T00:00:00.123456Z',due_at:'2030-01-01T00:02:00.123456Z',second_reminder_at:'2030-01-01T00:05:00.123456Z',expires_at:'2030-01-01T00:10:00.123456Z',observed_at:observed,
  reminders:[{ordinal:1,due_at:'2030-01-01T00:02:00.123456Z',recorded_at:null},{ordinal:2,due_at:'2030-01-01T00:05:00.123456Z',recorded_at:null}],maintenance:'SCHEDULED',resolution:null,closure:null,context_hold:null,can_resolve:true,can_cancel:true,
});
export const context=(v=escalation()):EscalationContext=>({workspace:v.workspace_id,escalation:v.escalation_id,conversation:v.conversation_id,client:v.client_id});
export const body=(operation:EscalationOperation='RESOLVE',v=escalation(),answer='  Решение\ne\u0301 🎨  '):EscalationBody=>({expected_conversation_id:v.conversation_id,expected_client_id:v.client_id,expected_escalation_version:v.version,expected_control_generation:v.current_context.control_generation,expected_context_version:v.current_context.context_version,...(operation==='RESOLVE'?{answer_text:answer}:{})});
export const page=(...items:EscalationView[]):EscalationPage=>({items,next_cursor:null,observed_at:items[0]?.observed_at??observed});
export const receipt=(operation:EscalationOperation='RESOLVE',b=body(operation),c=context()):EscalationReceipt=>({outcome:'ACCEPTED',result:{workspace_id:c.workspace,escalation_id:c.escalation,conversation_id:c.conversation,client_id:c.client,receipt_id:id(500),audit_event_id:id(501),operation,accepted_status:operation==='RESOLVE'?'RESOLVED':'CANCELLED',previous_version:'1',accepted_version:'2',accepted_context_version:String(BigInt(b.expected_context_version)+1n),control_generation:b.expected_control_generation,accepted_at:observed}});
export function terminal(operation:EscalationOperation='RESOLVE',v=escalation(),answer=body().answer_text!):EscalationView{return {...v,version:'2',status:operation==='RESOLVE'?'RESOLVED':'CANCELLED',validity:'TERMINAL',waiting:null,can_resolve:false,can_cancel:false,current_context:{...v.current_context,context_version:String(BigInt(v.current_context.context_version)+1n)},resolution:operation==='RESOLVE'?{answer_text:answer,actor_user_account_id:actor,completed_at:observed}:null,closure:operation==='CANCEL'?{reason:'OWNER_CANCELLED',actor_user_account_id:actor,completed_at:observed}:null};}
export const deferred=<T,>()=>{let resolve!:(value:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
