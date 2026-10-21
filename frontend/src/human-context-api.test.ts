import { afterEach, describe, expect, it, vi } from 'vitest';
import { HumanContextError, HumanContextState, ReconcileBody, humanContextApi, parseHumanContext, parseHumanContextError, parseObservationCursor, parseObservations, parseReconcileReceipt, reconcileBody, serializeReconcile } from './human-context-api';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const c={workspace:id(1),conversation:id(2),client:id(3)},at='2030-01-01T00:00:00.123456Z';
function state():HumanContextState{return {workspace_id:c.workspace,conversation_id:c.conversation,client_id:c.client,observed_at:at,control_mode:'HUMAN',control_generation:'9007199254740993',context_version:'9',policy:'ON',policy_epoch:'1',observation_epoch:'0',ingress_checkpoint:'4',input_state_hash:'a'.repeat(64),input_gap_limit_exceeded:false,has_unsequenced_context_input:false,current_revision:null,review_status:'BOOTSTRAP_REQUIRED',context_blockers:['CONTEXT_CONFIRMATION_REQUIRED'],resume_blockers:['CONTEXT_CONFIRMATION_REQUIRED'],history_truncated:false,coverage_status:'UNCONFIRMED',pending_context_input:false,has_failed_context_input:false,unreviewed_failed_context_input:false,automation_work:{state:'IDLE',reason:null,job_id:null,turn_id:null,observed_at:at},manual_delivery:{has_dispatching:false,has_unknown:false}};}
const body=()=>reconcileBody(state(),'OWNER_TEXT','  e\u0301 🎨\n  ','NONE');
const receipt=(b:ReconcileBody=body())=>({outcome:'ACCEPTED',result:{workspace_id:c.workspace,conversation_id:c.conversation,client_id:c.client,receipt_id:id(10),revision_id:id(10),revision_no:'1',previous_revision_id:b.expected_revision_id,audit_event_id:id(11),control_generation:b.expected_control_generation,previous_context_version:b.expected_context_version,accepted_context_version:String(BigInt(b.expected_context_version)+1n),policy_epoch:b.expected_policy_epoch,observation_epoch:b.expected_observation_epoch,reviewed_ingress_checkpoint:b.expected_ingress_checkpoint,reviewed_input_state_hash:b.expected_input_state_hash,disposition:b.disposition,source_media:b.source_media,coverage:'OWNER_ASSERTED_TEXT_ONLY',accepted_at:at}});
const token=(v:unknown)=>btoa(JSON.stringify(v)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const cursor=(after='1',through='2')=>token({v:1,ws:c.workspace,C:c.conversation,Client:c.client,P:'1',through_N:through,after_N:after});
const item=(epoch='1',preview:unknown={kind:'TEXT',text:'  \n  '},source_kind='NEW')=>({observation_id:id(Number(epoch)+20),epoch,classification:'NATIVE_CANDIDATE',observed_at:at,source_kind,preview,coverage:'PROVIDER_OBSERVATION_ONLY'});
const page=(items:unknown[]=[item()],next_cursor:string|null=null)=>({items,next_cursor,through_epoch:'2',current_epoch:'2',observed_at:at});
afterEach(()=>vi.unstubAllGlobals());
describe('human-context exact wire boundary',()=>{
  it('preserves bigint decimals, zero epochs, exact Unicode and all three dispositions',()=>{
    expect(parseHumanContext(state(),c)).toEqual(state());
    for(const disposition of ['OWNER_TEXT','CANONICAL_SUFFICIENT','UNRESOLVED'] as const){const b=reconcileBody(state(),disposition,disposition==='OWNER_TEXT'?body().text:null,disposition==='CANONICAL_SUFFICIENT'?'NONE':'UNAVAILABLE');expect(JSON.parse(serializeReconcile(b))).toEqual(b);expect(parseReconcileReceipt(receipt(b),c,b).result.disposition).toBe(disposition);}
    expect(JSON.parse(serializeReconcile(body())).text).toBe('  e\u0301 🎨\n  ');
  });
  it('keeps policy OFF/PAUSED, full revision/coverage and ordered blockers coherent',()=>{
    const s=state();expect(parseHumanContext({...s,policy:'OFF_UNUSED',policy_epoch:'0',context_blockers:['POLICY_INACTIVE'],resume_blockers:[],review_status:'POLICY_INACTIVE'},c).policy).toBe('OFF_UNUSED');
    const paused={...s,policy:'PAUSED',control_mode:'AI',context_blockers:['POLICY_PAUSED','CONTEXT_CONFIRMATION_REQUIRED'],resume_blockers:['POLICY_PAUSED','HUMAN_REQUIRED','CONTEXT_CONFIRMATION_REQUIRED'],review_status:'POLICY_PAUSED'};
    expect(parseHumanContext(paused,c).policy).toBe('PAUSED');
    const r={revision_id:id(10),revision_no:'1',previous_revision_id:null,actor_user_account_id:id(4),accepted_at:at,disposition:'CANONICAL_SUFFICIENT',text:null,source_media:'NONE',coverage:'OWNER_ASSERTED_TEXT_ONLY',confirmed_generation:s.control_generation,accepted_context_version:'9',policy_epoch:'1',observation_epoch:'0',reviewed_ingress_checkpoint:'4',reviewed_input_state_hash:'a'.repeat(64)};
    expect(parseHumanContext({...s,current_revision:r,context_blockers:['CONTEXT_COVERAGE_REQUIRED'],resume_blockers:['CONTEXT_COVERAGE_REQUIRED'],review_status:'COVERAGE_REQUIRED',history_truncated:true,coverage_status:'CANONICAL_TRUNCATED'},c).current_revision).toEqual(r);
  });
  it.each([{workspace_id:id(99)},{conversation_id:id(99)},{client_id:id(99)},{extra:true},{context_version:'01'},{policy_epoch:'9223372036854775808'},{observation_epoch:0},{observed_at:'2030-02-30T00:00:00.123456Z'},{input_state_hash:'A'.repeat(64)},{current_revision:undefined},{manual_delivery:{has_dispatching:false}},{input_gap_limit_exceeded:0},{context_blockers:['NEW_OBSERVATION','CONTEXT_CONFIRMATION_REQUIRED']},{context_blockers:['CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_CONFIRMATION_REQUIRED']},{resume_blockers:[]},{review_status:'CONFIRMED'},{coverage_status:'OWNER_TEXT'},{unreviewed_failed_context_input:true},{pending_context_input:true},{policy:'PAUSED'},{automation_work:{state:'IDLE',reason:'CONTEXT_INPUT_PENDING',job_id:null,turn_id:null,observed_at:at}}])('rejects malformed/foreign/inconsistent current projection %#',delta=>expect(()=>parseHumanContext({...state(),...delta},c)).toThrow(HumanContextError));
  it.each(['WAITING_CONTEXT','OPERATOR_REQUIRED'] as const)('accepts exact %s work without treating it as a retry permission',work=>{
    const value={...state(),automation_work:{state:work,reason:work==='WAITING_CONTEXT'?'CONTEXT_INPUT_PENDING':'CONTEXT_WAIT_EXHAUSTED',job_id:id(50),turn_id:id(51),observed_at:at}};expect(parseHumanContext(value,c).automation_work.state).toBe(work);
    expect(()=>parseHumanContext({...value,automation_work:{...value.automation_work,observed_at:'2030-01-01T00:00:01.123456Z'}},c)).toThrow();
  });
  it.each(['',' ','\u0085','\0','\ud800','\udfff','x'.repeat(4097)])('rejects unusable owner text %# without normalizing it',text=>expect(()=>serializeReconcile({...body(),text})).toThrow());
  it.each(['OWNER_TEXT','UNRESOLVED'] as const)('measures 4096/4097 bytes including Unicode, escapes and the entire %s envelope',disposition=>{
    for(const prefix of ['e\u0301 🎨','"\\\n','text']){let b={...body(),disposition,text:prefix};const used=new TextEncoder().encode(JSON.stringify(b)).length;b={...b,text:prefix+'x'.repeat(4096-used)};expect(new TextEncoder().encode(serializeReconcile(b)).length).toBe(4096);expect(()=>serializeReconcile({...b,text:b.text+'x'})).toThrow('BODY_TOO_LARGE');}
  });
  it('strictly binds every accepted result field to the original intention',()=>{
    for(const [field,value]of Object.entries({workspace_id:id(99),conversation_id:id(99),client_id:id(99),receipt_id:id(99),previous_revision_id:id(99),revision_no:'2',control_generation:'1',previous_context_version:'10',accepted_context_version:'12',policy_epoch:'2',observation_epoch:'1',reviewed_ingress_checkpoint:'5',reviewed_input_state_hash:'b'.repeat(64),source_media:'UNAVAILABLE',disposition:'UNRESOLVED',coverage:'TELEGRAM_COMPLETE',accepted_at:'bad',extra:true}))expect(()=>parseReconcileReceipt({...receipt(),result:{...receipt().result,[field]:value}},c,body())).toThrow('INVALID_RESPONSE');
  });
  it('accepts all preview unions, whitespace observation, empty/null caption and strict DELETE count',()=>{
    for(const [preview,kind]of [[{kind:'TEXT',text:' \n '},'NEW'],[{kind:'PHOTO',caption:'',image_availability:'NATIVE_UNAVAILABLE'},'EDIT'],[{kind:'PHOTO',caption:null,image_availability:'NATIVE_UNAVAILABLE'},'NEW'],[{kind:'UNSUPPORTED',reason:'AMBIGUOUS_ORIGIN'},'EDIT'],[{kind:'DELETE',target_count:100},'DELETE']] as const)expect(parseObservations(page([item('1',preview,kind)]),c).items).toHaveLength(1);
  });
  it.each([{kind:'TEXT',text:''},{kind:'TEXT',text:'\ud800'},{kind:'PHOTO',caption:null,image_availability:'READY'},{kind:'PHOTO',caption:'\0',image_availability:'NATIVE_UNAVAILABLE'},{kind:'DELETE',target_count:true},{kind:'DELETE',target_count:101},{kind:'UNSUPPORTED',reason:'OTHER'},{kind:'VIDEO',reason:'UNSUPPORTED_CONTENT'}])('rejects malformed preview %#',preview=>expect(()=>parseObservations(page([item('1',preview,preview.kind==='DELETE'?'DELETE':'NEW')]),c)).toThrow());
  it('validates canonical ordered/scoped cursor bytes and ascending frozen-through pagination',()=>{
    const first=page([item()],cursor());expect(parseObservations(first,c).next_cursor).toBe(cursor());
    expect(parseObservations({...page([item('2')]),current_epoch:'3'},c,cursor()).current_epoch).toBe('3');
    for(const bad of [cursor()+'=',token({v:1,ws:id(99),C:c.conversation,Client:c.client,P:'1',through_N:'2',after_N:'1'}),token({ws:c.workspace,v:1,C:c.conversation,Client:c.client,P:'1',through_N:'2',after_N:'1'}),cursor('3'),token({v:true,ws:c.workspace,C:c.conversation,Client:c.client,P:'1',through_N:'2',after_N:'1'})])expect(()=>parseObservationCursor(bad,c)).toThrow();
    for(const value of [page([item('2'),item('1')]),page([item(),item()]),page([item('3')]),page([],cursor()),{...page(),current_epoch:'1'},{...page(),items:[{...item(),source_kind:'DELETE'}]}])expect(()=>parseObservations(value,c)).toThrow();
  });
  it('keeps errors closed by exact status and does not accept generic success/error JSON',()=>{
    for(const code of ['STALE_STATE','CONTEXT_CURSOR_STALE','CONTEXT_POLICY_PAUSED','CONTEXT_INPUT_PENDING','HUMAN_REQUIRED'])expect(parseHumanContextError({error:{code}},409).code).toBe(code);
    for(const [v,status]of [[{error:{code:'CONTEXT_CURSOR_STALE'}},422],[{error:{code:'UNAVAILABLE',detail:'private'}},503],[{error:{code:'OTHER'}},409]])expect(()=>parseHumanContextError(v,status as number)).toThrow();
  });
});
describe('human-context HTTP commands',()=>{
  it('uses only the three accepted routes; exact frozen body/key and current CSRF, GET without writes',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(state()))).mockResolvedValueOnce(new Response(JSON.stringify(page()))).mockResolvedValueOnce(new Response(JSON.stringify(receipt())));vi.stubGlobal('fetch',fetch);
    await humanContextApi.read(c);await humanContextApi.observations(c);await humanContextApi.reconcile(c,body(),'same-key','csrf');
    expect(fetch.mock.calls.map(([url])=>url)).toEqual(['','/observations?limit=20','/reconcile'].map(s=>`/api/v1/workspaces/${c.workspace}/conversations/${c.conversation}/human-context${s}`));
    expect(fetch.mock.calls[2][1]).toMatchObject({credentials:'include',cache:'no-store',method:'POST',headers:{'Idempotency-Key':'same-key','X-CSRF-Token':'csrf'},body:JSON.stringify(body())});
  });
  it('refuses oversized or invalid bodies before fetch; invalid202/JSON remains ambiguous',async()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);expect(()=>humanContextApi.reconcile(c,{...body(),text:'🎨'.repeat(1500)},'key','csrf')).toThrow('BODY_TOO_LARGE');expect(fetch).not.toHaveBeenCalled();
    for(const response of [new Response(JSON.stringify(receipt()),{status:202}),new Response('broken',{status:200})]){fetch.mockResolvedValueOnce(response);await expect(humanContextApi.reconcile(c,body(),'key','csrf')).rejects.toThrow('INVALID_RESPONSE');}
  });
});
