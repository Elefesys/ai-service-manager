import { describe, expect, it, vi } from 'vitest';
import { billingApi, normalizeContact, parseAuditPage, parseBilling, parseBillingError, parseContactResult } from './billing-api';
import { billing, event, fail, ok, receipt, stamp, ws } from './billing-fixtures.test-helper';

describe('R4 generated OpenAPI consumer', () => {
  it('reads native reconciliation and all policy command Audit transitions without exposing private context',()=>{
    const reconciled={...event(50),object_type:'CONVERSATION',object_version:'9007199254740994',event_type:'HUMAN_CONTEXT_RECONCILED',payload:{revision_id:event(51).object_id,previous_revision_id:null,disposition:'OWNER_TEXT',source_media:'UNAVAILABLE',control_generation:'9007199254740993',previous_context_version:'9007199254740993',accepted_context_version:'9007199254740994',policy_epoch:'1',observation_epoch:'0',reviewed_ingress_checkpoint:'0'}};
    const policy={...event(52),object_type:'CHANNEL_CONNECTION',object_version:'1',event_type:'HUMAN_CONTEXT_POLICY_COMMANDED',actor_kind:'LOCAL_PROVISIONER',actor_user_account_id:null,payload:{receipt_id:event(53).object_id,operation:'ENABLE',change:'ENABLED',previous_policy:'OFF_UNUSED',accepted_policy:'ON',previous_policy_epoch:'0',accepted_policy_epoch:'1'}};
    for(const patch of [{},{disposition:'UNRESOLVED'},{disposition:'CANONICAL_SUFFICIENT',source_media:'NONE'}])expect(parseAuditPage({items:[{...reconciled,payload:{...reconciled.payload,...patch}},event()],next_cursor:null}).items).toHaveLength(2);
    const transitions=[policy,{...policy,payload:{...policy.payload,previous_policy:'ON',previous_policy_epoch:'1',change:'UNCHANGED'}},{...policy,payload:{...policy.payload,operation:'PAUSE',previous_policy:'ON',previous_policy_epoch:'1',accepted_policy:'PAUSED',change:'PAUSED'}},{...policy,payload:{...policy.payload,operation:'PAUSE',previous_policy:'PAUSED',previous_policy_epoch:'1',accepted_policy:'PAUSED',change:'UNCHANGED'}},{...policy,object_version:'2',payload:{...policy.payload,previous_policy:'PAUSED',previous_policy_epoch:'1',accepted_policy_epoch:'2'}}];
    expect(parseAuditPage({items:transitions,next_cursor:null}).items).toEqual(transitions);
    for(const v of [{...reconciled,actor_kind:'LOCAL_PROVISIONER'},{...reconciled,actor_user_account_id:null},{...reconciled,object_type:'MESSAGE'},{...reconciled,object_version:'2'},...[
      {revision_id:'bad'},{previous_revision_id:reconciled.payload.revision_id},{disposition:'CANONICAL_SUFFICIENT'},{accepted_context_version:'9007199254740995'},{policy_epoch:'0'},{observation_epoch:0},{text:'private'},{reviewed_input_state_hash:'a'.repeat(64)},
    ].map(p=>({...reconciled,payload:{...reconciled.payload,...p}})),{...policy,actor_kind:'USER_ACCOUNT'},{...policy,actor_user_account_id:event().actor_user_account_id},{...policy,object_type:'CONVERSATION'},...[
      {operation:'PAUSE'},{change:'UNCHANGED'},{previous_policy_epoch:'1'},{accepted_policy:'PAUSED'},{accepted_policy_epoch:'2'},{receipt_id:'bad'},{source_profile:{}},
    ].map(p=>({...policy,payload:{...policy.payload,...p}}))])expect(()=>parseAuditPage({items:[v],next_cursor:null})).toThrow('INVALID_RESPONSE');
  });
  it('accepts both Escalation decisions with mixed Audit and rejects cross-variant or answer payloads', () => {
    const resolve = {...event(6),object_type:'ESCALATION',object_version:'2',event_type:'ESCALATION_DECIDED',payload:{operation:'RESOLVE',status:'RESOLVED'}};
    const cancel = {...resolve,audit_event_id:event(7).audit_event_id,payload:{operation:'CANCEL',status:'CANCELLED'}};
    const message = {...event(3),object_type:'MESSAGE',event_type:'MESSAGE_SEND_REQUESTED',payload:{content_type:'TEXT'}};
    const control = {...event(4),object_type:'CONVERSATION',event_type:'CONVERSATION_RESUMED',payload:{previous_mode:'HUMAN',control_mode:'AI',previous_generation:'1',control_generation:'2'}};
    const items = [resolve,cancel,message,control,event()];
    expect(parseAuditPage({items,next_cursor:null})).toEqual({items,next_cursor:null});
    for (const item of [
      {...resolve,object_version:'1'}, {...resolve,object_type:'MESSAGE'}, {...resolve,actor_user_account_id:null},
      {...resolve,actor_kind:'LOCAL_PROVISIONER'}, {...resolve,payload:{operation:'RESOLVE',status:'CANCELLED'}},
      {...cancel,payload:{operation:'CANCEL',status:'RESOLVED'}}, {...cancel,payload:{operation:'CANCEL',status:'EXPIRED'}},
      {...resolve,payload:{...resolve.payload,answer_text:'private'}}, {...resolve,payload:{operation:'RESOLVE'}},
      {...resolve,escalation_id:resolve.object_id}, {...resolve,object_version:2},
    ]) expect(() => parseAuditPage({items:[item],next_cursor:null})).toThrow('INVALID_RESPONSE');
  });
  it('accepts exact CONTROL variants in mixed Audit and rejects incoherent counters/relations', () => {
    const takeover = {...event(4),object_type:'CONVERSATION',object_version:'9',event_type:'CONVERSATION_TAKEN_OVER',payload:{previous_mode:'AI',control_mode:'HUMAN',previous_generation:'9007199254740992',control_generation:'9007199254740993'}};
    const resume = {...takeover,audit_event_id:event(5).audit_event_id,event_type:'CONVERSATION_RESUMED',payload:{...takeover.payload,control_mode:'AI'}};
    const message = {...event(3),object_type:'MESSAGE',event_type:'MESSAGE_SEND_REQUESTED',payload:{content_type:'TEXT'}};
    const mixed = [resume,takeover,message,event()];
    expect(parseAuditPage({items:mixed,next_cursor:'next'})).toEqual({items:mixed,next_cursor:'next'});
    for (const item of [
      {...takeover,object_type:'MESSAGE'}, {...resume,actor_user_account_id:null}, {...resume,actor_kind:'LOCAL_PROVISIONER'},
      {...takeover,object_version:9}, {...takeover,payload:{...takeover.payload,control_mode:'AI'}},
      ...['0','01','+2','2\n','9223372036854775808',2,true,null].map(control_generation => ({...takeover,payload:{...takeover.payload,control_generation}})),
      {...takeover,payload:{...takeover.payload,control_generation:'9007199254740994'}},
      {...takeover,payload:{...takeover.payload,previous_mode:null}},
      {...takeover,payload:{...takeover.payload,activation_fence_seq:'11'}},
      {...takeover,payload:{control_mode:'HUMAN',previous_generation:'1',control_generation:'2'}},
    ]) expect(() => parseAuditPage({items:[item],next_cursor:null})).toThrow('INVALID_RESPONSE');
  });
  it('preserves zero, max bigint, non-v4/v7 UUIDs and microseconds exactly', () => {
    const b = billing('Name', '9223372036854775807'); b.decisions[1] = { ...b.decisions[1], type: 'LIMIT', limit: '9223372036854775807', reason: null };
    expect(parseBilling(b)).toEqual(b); expect(parseBilling(b).evaluated_at).toBe(stamp); expect(parseContactResult(receipt())).toEqual(receipt());
  });
  it('rejects extra/missing fields, numbers/overflow, uppercase UUID and malformed timestamps', () => {
    for (const b of [ { ...billing(), extra: true }, { ...billing(), account: { ...billing().account, version: 1 } }, { ...billing(), account: { ...billing().account, version: '9223372036854775808' } }, { ...billing(), workspace_id: 'AAAAAAAA-0000-0000-0000-000000000001' }, { ...billing(), evaluated_at: '2026-02-30T12:00:00.123456Z' }, { ...billing(), evaluated_at: '2026-09-20T12:00:00.123Z' }, { ...billing(), evaluated_at: stamp + '\n' } ]) expect(() => parseBilling(b)).toThrow('INVALID_RESPONSE');
    expect(() => parseContactResult({ ...receipt(), current_contact: 'leak' })).toThrow();
  });
  it('enforces tagged decisions, unique order, funding pair and safe plan revision', () => {
    const b = billing();
    for (const changes of [ { decisions: [{ key: 'a', type: 'LIMIT', reason: null, limit: 0 }] }, { decisions: [{ key: 'a', type: 'ENABLED', reason: 'NOT_ENTITLED', limit: null }] }, { decisions: [b.decisions[0],b.decisions[0]] }, { decisions: [...b.decisions].reverse() }, { subscription: { ...b.subscription, funding_mode: 'TRIAL' } } ]) expect(() => parseBilling({ ...b, ...changes })).toThrow();
  });
  it('implements scalar/padding/byte boundaries without normalization or Unicode trim', () => {
    expect(normalizeContact('  ' + '🎨'.repeat(200) + '  ')).toBe('🎨'.repeat(200));
    expect(normalizeContact('\u00a0Name\u00a0')).toBe('\u00a0Name\u00a0'); expect(normalizeContact('e\u0301')).not.toBe(normalizeContact('é'));
    for (const separator of ['\u2028','\u2029']) { expect(normalizeContact('  A ' + separator)).toBe('A ' + separator); expect(parseBilling(billing('A ' + separator)).account.contact_display_name).toBe('A ' + separator); }
    for (const name of [' ', '🎨'.repeat(201), 'a\n', 'a\t', 'a\u007f', '\ud800', '\udfff', '\0']) expect(() => normalizeContact(name)).toThrow('INVALID_REQUEST');
  });
  it('accepts only exact disjoint error unions and correct status codes', () => {
    expect(parseBillingError({ error: { code: 'UNAVAILABLE' } },503,true).stateReason).toBeUndefined();
    expect(parseBillingError({ error: { code: 'BILLING_STATE_UNAVAILABLE', state_reason: 'DATABASE_UNAVAILABLE' } },503,true).stateReason).toBe('DATABASE_UNAVAILABLE');
    for (const [body,status,structural] of [[{error:{code:'UNAVAILABLE',state_reason:null}},503,true],[{error:{code:'BILLING_STATE_UNAVAILABLE'}},503,true],[{error:{code:'BILLING_STATE_UNAVAILABLE',state_reason:'UNKNOWN'}},503,true],[{error:{code:'BILLING_STATE_UNAVAILABLE',state_reason:'DATABASE_UNAVAILABLE'}},503,false],[{error:{code:'STALE_STATE'}},200,false]] as const) expect(() => parseBillingError(body,status,structural)).toThrow();
  });
  it('rejects Audit contact values, wrong actor/payload, extra fields and oversized page', () => {
    const a = event(); expect(parseAuditPage({items:[a],next_cursor:'opaque_ABC-123'}).items[0]).toEqual(a);
    for (const item of [{...a,payload:{...a.payload,contact:'private'}},{...a,actor_user_account_id:null},{...a,payload:{changed_fields:[]}},{...a,secret:'private'}]) expect(() => parseAuditPage({items:[item],next_cursor:null})).toThrow();
    expect(() => parseAuditPage({items:Array(11).fill(a),next_cursor:null})).toThrow();
  });
  it('parses mixed billing and messaging Audit without a generic payload fallback', () => {
    const contact = event();
    const provision = {...event(2), event_type:'WORKSPACE_BILLING_PROVISIONED',actor_kind:'LOCAL_PROVISIONER',actor_user_account_id:null,payload:{}};
    const message = {...event(3),object_type:'MESSAGE',event_type:'MESSAGE_SEND_REQUESTED',payload:{content_type:'TEXT'}};
    expect(parseAuditPage({items:[message,contact,provision],next_cursor:'opaque'}).items).toEqual([message,contact,provision]);
    for (const item of [
      {...message,object_type:'WORKSPACE_BILLING_ACCOUNT'}, {...message,object_version:'2'},
      {...message,actor_kind:'LOCAL_PROVISIONER'}, {...message,actor_user_account_id:null},
      {...message,object_id:'invalid'}, {...message,payload:{content_type:'IMAGE_REFERENCE'}},
      {...message,payload:{content_type:'TEXT',text:'private'}}, {...message,payload:{}},
      {...contact,object_type:'MESSAGE'}, {...provision,object_type:'MESSAGE'},
    ]) expect(() => parseAuditPage({items:[item],next_cursor:null})).toThrow('INVALID_RESPONSE');
  });
  it('passes opaque cursor and frozen PATCH body/key with credentials; rejects foreign snapshot', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(ok({items:[],next_cursor:null})).mockResolvedValueOnce(ok(receipt())).mockResolvedValueOnce(ok({...billing(),workspace_id:'00000000-0000-0000-0000-000000000009'})); vi.stubGlobal('fetch',fetch);
    await billingApi.audit(ws,'opaque_ABC-123'); const body={expected_version:'9223372036854775807',contact_display_name:'  Name  '}; await billingApi.save(ws,body,'test-key','csrf');
    expect(fetch.mock.calls[0][0]).toBe(`/api/v1/workspaces/${ws}/audit-events?limit=10&cursor=opaque_ABC-123`);
    expect(fetch.mock.calls[1][1]).toMatchObject({method:'PATCH',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':'csrf','Idempotency-Key':'test-key'},body:JSON.stringify(body)});
    await expect(billingApi.read(ws)).rejects.toThrow('INVALID_RESPONSE');
  });
  it('treats malformed success and bounded timeout as ambiguous failures', async () => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(ok({})).mockResolvedValueOnce(fail(409,'STALE_STATE')));
    await expect(billingApi.save(ws,{expected_version:'1',contact_display_name:'a'},'k','c')).rejects.toThrow('INVALID_RESPONSE');
    await expect(billingApi.save(ws,{expected_version:'1',contact_display_name:'a'},'k','c')).rejects.toThrow('STALE_STATE');
    vi.useFakeTimers();
    try {
      vi.stubGlobal('fetch',vi.fn((_url, init: RequestInit) => new Promise((_resolve,reject) => init.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))))));
      const operation=billingApi.read(ws); const assertion=expect(operation).rejects.toThrow('Aborted'); await vi.advanceTimersByTimeAsync(10_000); await assertion;
    } finally { vi.useRealTimers(); }
  });
});

describe('M3 channel material Audit',()=>{
  it('requires exact actor, accepted version and closed payload in mixed pages',()=>{
    const material={...event(12),event_type:'MESSAGE_MATERIAL_CHANGED',object_type:'MESSAGE',object_version:'2',actor_kind:'CHANNEL_EVENT',actor_user_account_id:null,payload:{target_id:event(13).object_id,source_receipt_id:event(14).object_id,previous_version:'1',accepted_version:'2',reason:'CONTENT_CHANGED'}};
    expect(parseAuditPage({items:[material,event()],next_cursor:null}).items).toHaveLength(2);
    for(const bad of [{...material,actor_kind:'USER_ACCOUNT'},{...material,actor_user_account_id:event().actor_user_account_id},{...material,object_version:'3'},{...material,payload:{...material.payload,previous_version:'2'}},{...material,payload:{...material.payload,reason:'OTHER'}},{...material,payload:{...material.payload,text:'private'}}])expect(()=>parseAuditPage({items:[bad],next_cursor:null})).toThrow();
  });
});
