import { afterEach, describe, expect, it, vi } from 'vitest';
import { ControlError, controlApi, parseControlError, parseControlReceipt, parseControlState } from './conversation-control-api';
import { controlBody, controlContext, controlReceipt, controlState, id, ok } from './messaging-fixtures.test-helper';

afterEach(()=>vi.unstubAllGlobals());
describe('accepted CONTROL DTOs and identity',()=>{
  it('preserves exact versions above Number precision and both delivery flags',()=>{
    const state={...controlState(),control_generation:'9223372036854775807',manual_delivery:{has_dispatching:true,has_unknown:true}};
    expect(parseControlState(state,controlContext())).toEqual(state);
    for(const operation of ['TAKEOVER','RESUME'] as const)for(const outcome of ['ACCEPTED','REPLAY'] as const){const receipt={...controlReceipt(operation),outcome};expect(parseControlReceipt(receipt,controlContext(),operation,controlBody())).toEqual(receipt);}
  });
  it.each(['0','01','-1','1e3','1 ','1\n','9223372036854775808',1,true,null])('rejects invalid version %s',value=>{
    expect(()=>parseControlState({...controlState(),context_version:value},controlContext())).toThrow(ControlError);
  });
  it.each([
    {workspace_id:id(90)},{conversation_id:id(90)},{client_id:id(90)},{control_mode:'AUTO'},
    {control_generation:undefined},{observed_at:'2030-02-30T00:00:00.123456Z'},{observed_at:'2030-01-01T00:00:00.123Z'},
    {manual_delivery:{has_dispatching:false}},{manual_delivery:{has_dispatching:0,has_unknown:false}},
    {manual_delivery:{has_dispatching:false,has_unknown:false,extra:true}},{extra:true},
  ])('rejects malformed or other-context state %#',delta=>{
    expect(()=>parseControlState({...controlState(),...delta},controlContext())).toThrow(ControlError);
  });
  it.each([
    {workspace_id:id(99)},{conversation_id:id(99)},{client_id:id(99)},{operation:'TAKEOVER'},{accepted_mode:'HUMAN'},
    {previous_mode:'AUTO'},{previous_generation:'1'},{accepted_generation:'9007199254740995'},{context_version:'1'},
    {receipt_id:'00000000-0000-4000-8000-00000000000A'},{audit_event_id:null},{accepted_at:'bad'},{extra:true},
  ])('rejects invalid receipt transition or original request binding %#',delta=>{
    const receipt=controlReceipt();expect(()=>parseControlReceipt({...receipt,result:{...receipt.result,...delta}},controlContext(),'RESUME',controlBody())).toThrow(ControlError);
  });
  it('rejects missing/extra envelope keys and non-string enum lookalikes',()=>{
    for(const receipt of [{result:controlReceipt().result},{...controlReceipt(),extra:true},{...controlReceipt(),outcome:['ACCEPTED']}])expect(()=>parseControlReceipt(receipt,controlContext(),'RESUME',controlBody())).toThrow(ControlError);
  });
  it('keeps strict control errors and structural503 separate',()=>{
    for(const code of ['STALE_STATE','IDEMPOTENCY_KEY_CONFLICT','CONTROL_VERSION_EXHAUSTED','NOT_ALLOWED','CONTEXT_POLICY_INACTIVE','CONTEXT_POLICY_PAUSED','HUMAN_REQUIRED','CONTEXT_CONFIRMATION_REQUIRED','CONTEXT_UNRESOLVED','CONTEXT_INPUT_PENDING','CONTEXT_INPUT_UNRESOLVED','CONTEXT_COVERAGE_REQUIRED'])expect(parseControlError({error:{code}},409).code).toBe(code);
    expect(parseControlError({error:{code:'BILLING_STATE_UNAVAILABLE',state_reason:'REVISION_INVALID'}},503).stateReason).toBe('REVISION_INVALID');
    for(const [body,status] of [[{error:{code:'NOT_ALLOWED',state_reason:null}},409],[{error:{code:'BILLING_STATE_UNAVAILABLE'}},503],[{error:{code:'BILLING_STATE_UNAVAILABLE',state_reason:['REVISION_INVALID']}},503],[{error:{code:'STALE_STATE'}},200],[{error:{code:'INVALID_RESPONSE'}},500],[{error:{code:'UNAVAILABLE'},extra:true},503]] as const)expect(()=>parseControlError(body,status)).toThrow(ControlError);
  });
});
describe('CONTROL requests',()=>{
  it('uses three exact routes, unchanged body/key and credentials; GET is read-only',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(ok(controlState())).mockResolvedValueOnce(ok(controlReceipt('TAKEOVER'))).mockResolvedValueOnce(ok(controlReceipt('RESUME')));vi.stubGlobal('fetch',fetch);
    const context=controlContext(),body=Object.freeze(controlBody());
    await controlApi.read(context);
    for(const operation of ['TAKEOVER','RESUME'] as const)await controlApi.command(context,operation,body,'frozen-key','current-csrf');
    expect(fetch.mock.calls.map(([url])=>url)).toEqual(['control','takeover','resume'].map(route=>`/api/v1/workspaces/${context.workspace}/conversations/${context.conversation}/${route}`));
    expect(fetch.mock.calls[0][1]).toEqual({credentials:'include',cache:'no-store',signal:expect.any(AbortSignal)});
    for(const [,options] of fetch.mock.calls.slice(1))expect(options).toEqual({method:'POST',credentials:'include',cache:'no-store',signal:expect.any(AbortSignal),headers:{'Content-Type':'application/json','X-CSRF-Token':'current-csrf','Idempotency-Key':'frozen-key'},body:JSON.stringify(body)});
  });
  it('never accepts M2 202, malformed success or wrong identity as CONTROL success',async()=>{
    for(const response of [ok(controlReceipt(),202),ok({...controlReceipt(),result:{...controlReceipt().result,client_id:id(99)}}),new Response('broken',{status:200})]){
      vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response));await expect(controlApi.command(controlContext(),'RESUME',controlBody(),'key','csrf')).rejects.toMatchObject({code:'INVALID_RESPONSE'});
    }
  });
  it('propagates abort without recovery writes',async()=>{
    const c=new AbortController();c.abort();const fetch=vi.fn().mockImplementation((_url,init)=>{expect(init.signal.aborted).toBe(true);throw new DOMException('Aborted','AbortError');});vi.stubGlobal('fetch',fetch);
    await expect(controlApi.read(controlContext(),c.signal)).rejects.toThrow();expect(fetch).toHaveBeenCalledTimes(1);
  });
});
