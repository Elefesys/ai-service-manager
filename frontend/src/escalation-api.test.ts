import { afterEach, describe, expect, it, vi } from 'vitest';
import { EscalationError, escalationApi, exactAnswer, parseEscalation, parseEscalationError, parseEscalationPage, parseEscalationReceipt } from './escalation-api';
import { actor, body, context, escalation, id, observed, page, receipt, terminal, workspace } from './escalation-fixtures.test-helper';

afterEach(()=>vi.unstubAllGlobals());
const ok=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
describe('accepted Escalation DTOs',()=>{
  it('accepts required empty page clock, nullable fields and every terminal shape',()=>{
    expect(parseEscalationPage(page(),workspace,'PENDING')).toEqual(page());
    for(const v of [escalation(),terminal(),terminal('CANCEL'),{...terminal('CANCEL'),status:'EXPIRED',closure:{reason:'DEADLINE_ELAPSED',actor_user_account_id:null,completed_at:observed}}])expect(parseEscalation(v,workspace)).toEqual(v);
    expect(parseEscalation(escalation(),workspace).current_context.control_generation).toBe('9007199254740995');
  });
  it.each(['workspace_id','escalation_id','conversation_id','client_id','turn_id','assignee_user_account_id','waiting','resolution','closure','observed_at','can_resolve'])('rejects a missing required %s',key=>{
    const v:Record<string,unknown>={...escalation()};delete v[key];expect(()=>parseEscalation(v,workspace)).toThrow('INVALID_RESPONSE');
  });
  it.each([
    {status:'UNKNOWN'},{policy:'PRODUCTION'},{reason:'INVENTED'},{question:'arbitrary question'},{version:1},{version:'2'},{can_resolve:'true'},{waiting:null},{resolution:{}},{closure:{}},{unexpected:null},
    {created_at:'2030-02-30T00:00:00.000000Z'},{observed_at:'2030-01-01T00:00:00.000Z'},{observed_at:'2030-01-01T00:00:00.000000+00:00'},{observed_at:'0000-01-01T00:00:00.000000Z'},{expires_at:'2030-01-01T00:00:00.000000Z'},
    {client_id:id(210).toUpperCase().replace('00000000','ABCDEFAB')},{maintenance:'DEAD'},{reminders:[]},
  ])('fails closed on malformed view %#',patch=>expect(()=>parseEscalation({...escalation(),...patch},workspace)).toThrow('INVALID_RESPONSE'));
  it.each([0,1,true,'0','01','+1','1e3',' 1','1\n','9223372036854775808'])('rejects noncanonical or overflowing counters %s',value=>{
    const v=escalation();expect(()=>parseEscalation({...v,current_context:{...v.current_context,context_version:value}},workspace)).toThrow('INVALID_RESPONSE');
    expect(()=>parseEscalation({...v,bound_context:{...v.bound_context,turn_revision:value}},workspace)).toThrow('INVALID_RESPONSE');
  });
  it('checks nested shapes, reminder order and closure/resolution actors',()=>{
    const v=escalation(),r=terminal(),c=terminal('CANCEL');
    for(const patch of [{bound_context:{...v.bound_context,fingerprint:'A'.repeat(64)}},{current_context:{...v.current_context,extra:1}},{reminders:[v.reminders[1],v.reminders[0]]},{reminders:[{...v.reminders[0],recorded_at:'bad'},v.reminders[1]]}])expect(()=>parseEscalation({...v,...patch},workspace)).toThrow();
    expect(()=>parseEscalation({...r,resolution:{...r.resolution,answer_text:'\u0000'}},workspace)).toThrow('INVALID_RESPONSE');
    expect(()=>parseEscalation({...c,closure:{...c.closure,actor_user_account_id:null}},workspace)).toThrow();
    expect(()=>parseEscalation({...c,closure:{...c.closure,reason:'CONTEXT_CHANGED'}},workspace)).toThrow();
  });
  it('keeps PENDING+EXPIRED and FAILED maintenance distinct from lifecycle',()=>{
    const v=escalation();
    for(const patch of [{maintenance:'FAILED' as const},{validity:'EXPIRED' as const,observed_at:v.expires_at,waiting:null,can_cancel:false,can_resolve:false},{validity:'ASSIGNEE_REVOKED' as const,waiting:null,can_resolve:false}])expect(parseEscalation({...v,...patch},workspace)).toEqual({...v,...patch});
  });
  it('binds each view to Workspace and selected canonical relation',()=>{
    for(const c of [{escalation:id(99)},{conversation:id(99)},{client:id(99)}])expect(()=>parseEscalation(escalation(),workspace,c)).toThrow();
    expect(()=>parseEscalation(escalation(),id(99))).toThrow();
  });
  it('requires page observed_at even empty and equal item clocks; enforces limit/filter',()=>{
    for(const v of [{items:[],next_cursor:null},{...page(),observed_at:null},{...page(escalation()),observed_at:'2030-01-01T00:01:01.123456Z'},{...page(),next_cursor:''},{...page(),next_cursor:'x'.repeat(1025)},{...page(),extra:1},page(...Array(11).fill(escalation()))])expect(()=>parseEscalationPage(v,workspace,'PENDING')).toThrow();
    expect(()=>parseEscalationPage(page(terminal()),workspace,'PENDING')).toThrow();
    expect(parseEscalationPage({...page(escalation()),next_cursor:'opaque_-cursor'},workspace,'ALL').next_cursor).toBe('opaque_-cursor');
  });
  it('binds saved acceptance to exact original operation/body, without Number rounding',()=>{
    for(const op of ['RESOLVE','CANCEL'] as const)for(const outcome of ['ACCEPTED','REPLAY'] as const){const r={...receipt(op),outcome};expect(parseEscalationReceipt(r,context(),op,body(op))).toEqual(r);}
    const r=receipt();for(const patch of [{workspace_id:id(99)},{escalation_id:id(99)},{conversation_id:id(99)},{client_id:id(99)},{operation:'CANCEL'},{accepted_status:'CANCELLED'},{previous_version:'2'},{accepted_context_version:'9007199254740997'},{control_generation:'9007199254740994'},{accepted_at:null},{extra:true}])expect(()=>parseEscalationReceipt({...r,result:{...r.result,...patch}},context(),'RESOLVE',body())).toThrow();
    expect(()=>parseEscalationReceipt({...r,outcome:'CURRENT'},context(),'RESOLVE',body())).toThrow();
  });
  it('preserves exact Unicode scalars, whitespace and non-normalized text',()=>{
    for(const value of ['  e\u0301 🎨\n','🎨'.repeat(512),'\ufeff'])expect(exactAnswer(value)).toBe(value);
    for(const value of ['', ' \n\u0085\u001c', 'x'.repeat(513), '\u0000', '\ud800', '\udfff', null, 1])expect(()=>exactAnswer(value)).toThrow('INVALID_REQUEST');
  });
  it.each([[401,'SESSION_REQUIRED'],[403,'CSRF_REJECTED'],[403,'ACCESS_DENIED'],[403,'ORIGIN_DENIED'],[404,'NOT_FOUND'],[409,'STALE_STATE'],[409,'ESCALATION_EXPIRED'],[409,'ESCALATION_FINAL'],[409,'VERSION_EXHAUSTED'],[409,'IDEMPOTENCY_KEY_CONFLICT'],[413,'BODY_TOO_LARGE'],[415,'UNSUPPORTED_MEDIA_TYPE'],[422,'INVALID_REQUEST'],[429,'RATE_LIMITED'],[500,'INTERNAL_ERROR'],[503,'UNAVAILABLE']] as const)('parses only the accepted error %s/%s',(status,code)=>expect(parseEscalationError({error:{code}},status)).toMatchObject({status,code}));
  it('rejects wrong status/code and arbitrary nested error fields',()=>{
    for(const value of [{error:{code:'STALE_STATE'}},{error:{code:'UNAVAILABLE',detail:'private'}},{error:{code:'BILLING_STATE_UNAVAILABLE'}},{error:'UNAVAILABLE'}])expect(()=>parseEscalationError(value,503)).toThrow('INVALID_RESPONSE');
  });
});
describe('four routes',()=>{
  it('sends bounded list/filter/opaque cursor, detail without query, exact POST with cookie/CSRF/key and no If-Match',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(ok(page())).mockResolvedValueOnce(ok(page())).mockResolvedValueOnce(ok(escalation())).mockResolvedValueOnce(ok(receipt())).mockResolvedValueOnce(ok(receipt('CANCEL')));vi.stubGlobal('fetch',fetch);
    await escalationApi.list(workspace);await escalationApi.list(workspace,'ALL','opaque_cursor');await escalationApi.read(context());
    await escalationApi.command(context(),'RESOLVE',body(),'key:one','csrf');await escalationApi.command(context(),'CANCEL',body('CANCEL'),'key:two','csrf');
    const root=`/api/v1/workspaces/${workspace}/escalations`;
    expect(fetch.mock.calls.map(c=>c[0])).toEqual([`${root}?limit=10&status=PENDING`,`${root}?limit=10&status=ALL&cursor=opaque_cursor`,`${root}/${context().escalation}`,`${root}/${context().escalation}/resolve`,`${root}/${context().escalation}/cancel`]);
    for(const [,init] of fetch.mock.calls)expect(init).toMatchObject({credentials:'include',cache:'no-store',signal:expect.any(AbortSignal)});
    expect(fetch.mock.calls[2][1].body).toBeUndefined();
    expect(fetch.mock.calls[3][1]).toMatchObject({method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':'csrf','Idempotency-Key':'key:one'},body:JSON.stringify(body())});
    expect(fetch.mock.calls[4][1].body).toBe(JSON.stringify(body('CANCEL')));expect(fetch.mock.calls[4][1].body).not.toContain('answer');
    expect(fetch.mock.calls[3][1].body).not.toContain(actor);
  });
  it.each([202,204,201])('does not accept status %s as command success',async status=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(status===204?null:JSON.stringify(receipt()),{status})));
    await expect(escalationApi.command(context(),'RESOLVE',body(),'key','csrf')).rejects.toBeInstanceOf(EscalationError);
  });
  it('propagates cancellation and rejects malformed JSON as ambiguous response',async()=>{
    const c=new AbortController();c.abort();const fetch=vi.fn().mockResolvedValue(new Response('not-json'));vi.stubGlobal('fetch',fetch);
    await expect(escalationApi.read(context(),c.signal)).rejects.toMatchObject({status:502,code:'INVALID_RESPONSE'});expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
  });
});
