import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConfigurationError, configurationApi, parseActive, parseBundle, parseCommand, parseConfigurationError, parseDraft, parsePreview, SaveSource, KnowledgeOperation, KnowledgeBody, knowledgeApi, normalizeSource, validateKnowledgeCommand, parseKnowledgeState, parseKnowledgeCommand } from './configuration-api';
import { active, actor, bundle, businessId, command, draft, ok, preview, releaseId, workspace, sourceId, revisionId, buildId, knowledgeState, knowledgeSource, knowledgeCommand, emptyReadyBuild, emptyBuildId } from './configuration-fixtures.test-helper';
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
  it('treats the linked-build publication refusal as a definite closed 409 without retry',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValue(ok({error:{code:'KNOWLEDGE_BUILD_REQUIRED'}},409));
    await expect(configurationApi.command(workspace,businessId,'PUBLISH',{expected_draft_version:'1',expected_activation_version:'1'},'joint-required','csrf')).rejects.toMatchObject({status:409,code:'KNOWLEDGE_BUILD_REQUIRED'});
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(()=>parseConfigurationError({error:{code:'KNOWLEDGE_BUILD_REQUIRED'}},503)).toThrow('INVALID_RESPONSE');
  });

});

describe('knowledge owner wire',()=>{
  const save=():SaveSource=>({schema_version:1,source_id:null,expected_source_version:'0',title:'Памятка',format:'MARKDOWN',text:'  Cafe\u0301\r\nowner source  ',source_label:'Владелец',author_label:null,service_id:null,category:null,claim_key:null,effective_from:null,effective_until:null});
  it('keeps raw input for the server normalization and parses a bounded preview without private fields',()=>{
    expect(normalizeSource(save().text)).toBe('Café\nowner source');validateKnowledgeCommand('KNOWLEDGE_SAVE',save());
    const state={...knowledgeState(),sources:[knowledgeSource()]};
    expect(parseKnowledgeState(state)).toEqual(state);
    for(const raw of [
      {...state,profile_id:'other'},
      {...state,sources:[{...knowledgeSource(),ticket:'private'}]},
      {...state,sources:[{...knowledgeSource(),preview:{chunks:[{ordinal:0,text:'different',sha256:'a'.repeat(64)}],issues:[]}}]},
      {...state,sources:Array(9).fill(knowledgeSource())},
      {...state,embedding_mode:'PROVIDER'},
    ])expect(()=>parseKnowledgeState(raw)).toThrow('INVALID_RESPONSE');
  });
  it('rejects extra authority fields and UTF8 overflows before issuing HTTP',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch');
    for(const bad of [{...save(),actor_user_account_id:actor},{...save(),text:'€'.repeat(683)},{...save(),effective_from:'2026-02-31T00:00:00.000000Z'}]){
      await expect(knowledgeApi.command(workspace,businessId,'KNOWLEDGE_SAVE',bad as SaveSource,'key','csrf')).rejects.toThrow('INVALID_RESPONSE');
    }
    validateKnowledgeCommand('KNOWLEDGE_SAVE',{...save(),text:'€'.repeat(682)});
    expect(fetch).not.toHaveBeenCalled();
  });
  it('uses eight closed routes with one CSRF/idempotency envelope and validates scope',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(ok(knowledgeState()));
    await knowledgeApi.state(workspace,businessId);
    const commands:[KnowledgeOperation,KnowledgeBody,string?][]=[
      ['KNOWLEDGE_SAVE',save()],
      ['KNOWLEDGE_CONFIRM',{schema_version:1,expected_source_version:'1',revision_id:revisionId,canonical_sha256:'a'.repeat(64)},sourceId],
      ['KNOWLEDGE_REVOKE',{schema_version:1,expected_source_version:'2',expected_activation_version:'0'},sourceId],
      ['KNOWLEDGE_DELETE',{schema_version:1,expected_source_version:'3',expected_activation_version:'0'},sourceId],
      ['KNOWLEDGE_BUILD_CREATE',{schema_version:1,expected_sources_hash:'b'.repeat(64),revision_ids:[revisionId]}],
      ['KNOWLEDGE_PUBLISH',{schema_version:1,expected_draft_version:'1',expected_activation_version:'0',build_id:buildId,expected_build_version:'3'}],
      ['KNOWLEDGE_ROLLBACK',{schema_version:1,expected_activation_version:'1',release_id:releaseId}],
    ];
    for(const [op,body,source]of commands){
      fetch.mockResolvedValueOnce(ok(knowledgeCommand(op)));
      await knowledgeApi.command(workspace,businessId,op,body,'exact-key','csrf',source);
    }
    expect(fetch.mock.calls.map(c=>String(c[0]).split('/knowledge')[1])).toEqual(['','/sources',`/sources/${sourceId}/confirm`,`/sources/${sourceId}/revoke`,`/sources/${sourceId}/delete`,'/builds','/publish','/rollback']);
    for(const [,init]of fetch.mock.calls.slice(1))expect(init).toMatchObject({method:'POST',credentials:'include',cache:'no-store',headers:{'X-CSRF-Token':'csrf','Idempotency-Key':'exact-key'}});
    fetch.mockResolvedValueOnce(ok({...knowledgeState(),business_id:actor}));
    await expect(knowledgeApi.state(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');
    expect(()=>parseKnowledgeCommand({...knowledgeCommand(),ticket:'private'})).toThrow('INVALID_RESPONSE');
  });
  it('forbids a source ID inside confirmation body and handles only closed knowledge errors',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch');
    await expect(knowledgeApi.command(workspace,businessId,'KNOWLEDGE_CONFIRM',{schema_version:1,expected_source_version:'1',revision_id:revisionId,canonical_sha256:'a'.repeat(64),source_id:sourceId} as never,'key','csrf',sourceId)).rejects.toThrow('INVALID_RESPONSE');
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockResolvedValueOnce(ok({error:{code:'CHUNK_LIMIT'}},422));
    await expect(knowledgeApi.command(workspace,businessId,'KNOWLEDGE_BUILD_CREATE',{schema_version:1,expected_sources_hash:'b'.repeat(64),revision_ids:[revisionId]},'key','csrf')).rejects.toMatchObject({status:422,code:'CHUNK_LIMIT'});
    fetch.mockResolvedValueOnce(ok({error:{code:'RAW_PROVIDER_PRIVATE'}},503));
    await expect(knowledgeApi.state(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');
  });
  it('sends an explicit empty build and reads its zero-reservation READY state',async()=>{
    const empty=emptyReadyBuild(),state={...knowledgeState(),builds:[empty]};
    const fetch=vi.spyOn(globalThis,'fetch').mockResolvedValueOnce(ok(knowledgeCommand('KNOWLEDGE_BUILD_CREATE',{build_id:emptyBuildId,build_version:'1'}))).mockResolvedValueOnce(ok(state));
    await knowledgeApi.command(workspace,businessId,'KNOWLEDGE_BUILD_CREATE',{schema_version:1,expected_sources_hash:state.sources_hash,revision_ids:[]},'explicit-empty','csrf');
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body)).revision_ids).toEqual([]);
    expect(await knowledgeApi.state(workspace,businessId)).toEqual(state);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

});


it('accepts the closed portfolio publication guard without widening other error codes',()=>{expect(parseConfigurationError({error:{code:'PORTFOLIO_BUILD_REQUIRED'}},409)).toEqual(new ConfigurationError(409,'PORTFOLIO_BUILD_REQUIRED'));});
