import { afterEach, describe, expect, it, vi } from 'vitest';
import { configurationApi, parseActive, parseBundle, parseCommand, parseConfigurationError, parseDraft, parsePreview } from './configuration-api';
import { active, actor, bundle, businessId, command, draft, ok, preview, releaseId, workspace } from './configuration-fixtures.test-helper';
afterEach(()=>vi.restoreAllMocks());
describe('configuration owner wire',()=>{
  it('preserves independent modes, null unknowns, sources and explicit unpublished state',()=>{
    expect(parseBundle(bundle())).toEqual(bundle());expect(parseDraft(draft())).toEqual(draft());expect(parseActive(active())).toEqual(active());expect(parsePreview(preview())).toEqual(preview());expect(parseCommand(command())).toEqual(command());expect(parseActive(active(bundle(),'1'))).toEqual(active(bundle(),'1'));
  });
  it('keeps shape-valid invalid modes for server validation, without changing them',()=>{const b=bundle();b.services[0].price.mode='OTHER';expect(parseBundle(b).services[0].price.mode).toBe('OTHER');});
  it.each([
    ()=>({...draft(),extra:'private'}),()=>({...draft(),draft_version:1}),()=>({...draft(),draft_version:'01'}),()=>({...draft(),activation_version:'9223372036854775808'}),()=>({...draft(),activation_version:'1'}),()=>({...draft(),bundle:null}),()=>({...draft(),business_id:'forged'}),()=>({...draft(),schema_version:true}),
  ])('rejects malformed or incoherent draft %#',factory=>expect(()=>parseDraft(factory())).toThrow('INVALID_RESPONSE'));
  it('rejects hidden fields, unsafe numbers, invalid Unicode and excessive data',()=>{
    for(const mutate of [(b:ReturnType<typeof bundle>)=>Object.assign(b.services[0].price,{hidden:1}),(b:ReturnType<typeof bundle>)=>{b.services[0].deposit.percent=Number.NaN;},(b:ReturnType<typeof bundle>)=>{b.faqs[0].answer='\ud800';},(b:ReturnType<typeof bundle>)=>{b.rules[0].value=1e12;},(b:ReturnType<typeof bundle>)=>{b.faqs=Array(13).fill(b.faqs[0]);},(b:ReturnType<typeof bundle>)=>{b.faqs=Array.from({length:8},(_,i)=>({...b.faqs[0],id:`faq${i}`,answer:'я'.repeat(500)}));}]){const b=bundle();mutate(b);expect(()=>parseBundle(b)).toThrow('INVALID_RESPONSE');}
  });
  it('rejects incomplete active provenance and contradictory preview statuses',()=>{
    for(const bad of [{...active(bundle(),'1'),published_by:null},{...active(),release_id:releaseId},{...active(bundle(),'1'),published_at:'2026-02-31T00:00:00.000000Z'},{...active(bundle(),'1'),structured_rules_authoritative:false}])expect(()=>parseActive(bad)).toThrow('INVALID_RESPONSE');
    const p=preview();p.validation.valid=false;expect(()=>parsePreview(p)).toThrow('INVALID_RESPONSE');
  });
  it('sends six fixed owner routes with no-store credentials, CSRF and exact replay body/key',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(ok(draft())).mockResolvedValueOnce(ok(active())).mockResolvedValueOnce(ok(preview())).mockResolvedValueOnce(ok(command())).mockResolvedValueOnce(ok(command('PUBLISH','1','1',releaseId))).mockResolvedValueOnce(ok(command('ROLLBACK','1','2',releaseId)));
    await configurationApi.draft(workspace,businessId);await configurationApi.active(workspace,businessId);await configurationApi.preview(workspace,businessId);
    await configurationApi.command(workspace,businessId,'EDIT',{expected_draft_version:'1',bundle:bundle()},'same-key','csrf');await configurationApi.command(workspace,businessId,'PUBLISH',{expected_draft_version:'1',expected_activation_version:'0'},'publish','csrf');await configurationApi.command(workspace,businessId,'ROLLBACK',{expected_activation_version:'1',release_id:releaseId},'rollback','csrf');
    expect(fetch.mock.calls.map(c=>String(c[0]).split('/').at(-1))).toEqual(['draft','active','preview','draft','publish','rollback']);
    for(const [,init]of fetch.mock.calls){expect(init?.credentials).toBe('include');expect(init?.cache).toBe('no-store');}
    expect(fetch.mock.calls[3][1]).toMatchObject({method:'PUT',headers:{'X-CSRF-Token':'csrf','Idempotency-Key':'same-key'},body:JSON.stringify({expected_draft_version:'1',bundle:bundle()})});
  });
  it('rejects cross-Business/Workspace responses and wrong command operation',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(ok({...draft(),workspace_id:actor})).mockResolvedValueOnce(ok({...active(),business_id:actor})).mockResolvedValueOnce(ok({...preview(),state:{...draft(),business_id:actor}})).mockResolvedValueOnce(ok(command('ROLLBACK')));
    await expect(configurationApi.draft(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');await expect(configurationApi.active(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');await expect(configurationApi.preview(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');await expect(configurationApi.command(workspace,businessId,'PUBLISH',{expected_draft_version:'1',expected_activation_version:'0'},'publish','csrf')).rejects.toThrow('INVALID_RESPONSE');expect(fetch).toHaveBeenCalledTimes(4);
  });
  it('fails local oversize/extra command fields before HTTP and closes error/status combinations',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch');await expect(configurationApi.command(workspace,businessId,'EDIT',{expected_draft_version:'1',bundle:bundle(),sql:'drop'} as never,'key','csrf')).rejects.toThrow('INVALID_RESPONSE');expect(fetch).not.toHaveBeenCalled();
    expect(parseConfigurationError({error:{code:'ROLLBACK_NOT_ALLOWED'}},409).code).toBe('ROLLBACK_NOT_ALLOWED');expect(()=>parseConfigurationError({error:{code:'ACCESS_DENIED'}},200)).toThrow('INVALID_RESPONSE');expect(()=>parseConfigurationError({error:{code:'UNKNOWN',secret:'raw'}},503)).toThrow('INVALID_RESPONSE');
  });
  it('propagates cancellation and invalid-body uncertainty without raw payload',async()=>{
    const c=new AbortController();c.abort();const fetch=vi.spyOn(globalThis,'fetch').mockImplementation(async(_url,init)=>{expect(init?.signal?.aborted).toBe(true);throw new DOMException('Aborted','AbortError');});await expect(configurationApi.draft(workspace,businessId,c.signal)).rejects.toThrow('Aborted');fetch.mockResolvedValue(new Response('private invalid body'));await expect(configurationApi.active(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');
  });
});
