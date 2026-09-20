import { describe, expect, it, vi } from 'vitest';
import { billingApi, normalizeContact, parseAuditPage, parseBilling, parseBillingError, parseContactResult } from './billing-api';
import { billing, event, fail, ok, receipt, stamp, ws } from './billing-fixtures.test-helper';

describe('R4 generated OpenAPI consumer', () => {
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
