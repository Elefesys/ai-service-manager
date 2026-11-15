import { describe, expect, it, vi } from 'vitest';
import { CommandBody, Operation, PortfolioError, Target, parseConversationState, parseOwnerState, parseAnalysis, portfolioApi, validatePortfolioCommand } from './portfolio-api';
import { assetId, versionId, uploadId, itemId, itemRevision, portfolioBuildId, photo, portfolioItem, confirmedItem, portfolioBuild, ownerState, observation, referenceState, portfolioCommand, conversationId, clientId } from './portfolio-fixtures.test-helper';
import { businessId, workspace, ok } from './configuration-fixtures.test-helper';

const prefix=`/api/v1/workspaces/${workspace}/businesses/${businessId}/portfolio`;
const uploadTarget={asset:assetId,version:versionId,upload:uploadId};
const commands:[Operation,CommandBody,string,Target?][]=[
  ['PORTFOLIO_UPLOAD_CREATE',{schema_version:1,asset_id:null,expected_asset_version:'0',origin:'MY_WORK',mime_type:'image/png',size_bytes:6000,sha256:'a'.repeat(64)},'/assets/uploads'],
  ['PORTFOLIO_UPLOAD_FINALIZE',{schema_version:1,expected_asset_version:'1'},`/assets/${assetId}/versions/${versionId}/uploads/${uploadId}/finalize`,uploadTarget],
  ['PORTFOLIO_UPLOAD_ABANDON',{schema_version:1,expected_asset_version:'1'},`/assets/${assetId}/versions/${versionId}/uploads/${uploadId}/abandon`,uploadTarget],
  ['PORTFOLIO_SAVE',{schema_version:1,item_id:null,expected_item_version:'0',asset_id:assetId,description:'Цветок',attributes:{subject:null,styles:[],placement:null},service_id:null,analysis_id:null},'/items'],
  ['PORTFOLIO_CONFIRM',{schema_version:1,expected_item_version:'1',revision_id:itemRevision,canonical_sha256:'b'.repeat(64),confirm_my_work:true,show_permission:true},`/items/${itemId}/confirm`,{item:itemId}],
  ['PORTFOLIO_REVOKE',{schema_version:1,expected_item_version:'2',expected_activation_version:'0'},`/items/${itemId}/revoke`,{item:itemId}],
  ['PORTFOLIO_DELETE',{schema_version:1,expected_asset_version:'2',expected_activation_version:'0'},`/assets/${assetId}/delete`,{asset:assetId}],
  ['PORTFOLIO_BUILD_CREATE',{schema_version:1,expected_items_hash:'d'.repeat(64),revision_ids:[itemRevision]},'/builds'],
  ['PORTFOLIO_PUBLISH',{schema_version:1,expected_draft_version:'1',expected_activation_version:'0',knowledge_build_id:null,expected_knowledge_build_version:null,portfolio_build_id:portfolioBuildId,expected_portfolio_build_version:'3'},'/publish'],
  ['PORTFOLIO_ROLLBACK',{schema_version:1,expected_activation_version:'1',release_id:'b4444444-4444-4444-8444-444444444444'},'/rollback'],
];

describe('closed portfolio wire',()=>{
  it('validates owner sources, separate analysis, pending purge and an EMPTY build',()=>{
    const state={...ownerState(),assets:[{...photo(),analysis:observation()}],items:[confirmedItem()],builds:[portfolioBuild(true)],pending_purges:[{asset_id:assetId,version_id:versionId,state:'PURGE_PENDING',outcome:null,deadline:null}]};
    expect(parseOwnerState(state)).toEqual(state);
    expect(parseConversationState(referenceState())).toEqual(referenceState());
  });
  it.each(['storage_key','ticket','url'])('rejects private %s and cross-provenance promotion',key=>{
    expect(()=>parseOwnerState({...ownerState(),[key]:'private'})).toThrow('INVALID_RESPONSE');
    expect(()=>parseOwnerState({...ownerState(),assets:[{...photo(),origin:'CLIENT_REFERENCE'}]})).toThrow();
    expect(()=>parseOwnerState({...ownerState(),assets:[{...photo(),origin:'INSPIRATION'}],items:[confirmedItem()]})).toThrow();
  });
  it('rejects asset/item caps, invalid analysis authority/scale, and extra business fields',()=>{
    expect(()=>parseOwnerState({...ownerState(),assets:Array(9).fill(photo())})).toThrow();
    expect(()=>parseOwnerState({...ownerState(),items:Array(9).fill(portfolioItem())})).toThrow();
    for(const result of [{...observation().result,scale:'10cm'},{...observation().result,price:100},{...observation().result,uncertainty:[]}])expect(()=>parseAnalysis({...observation(),result})).toThrow();
  });
  it('rejects mixed conversation/client pins, more than top3 and unbounded reasons',()=>{
    const base=referenceState();expect(()=>parseConversationState({...base,media_pin:{...base.media_pin,client_id:assetId}})).toThrow();
    expect(()=>parseConversationState({...base,matches:{...base.matches,matches:Array(4).fill(base.matches!.matches[0])}})).toThrow();
    expect(()=>parseConversationState({...base,matches:{...base.matches,matches:[{...base.matches!.matches[0],text:'я'.repeat(81)}]}})).toThrow();
  });
  it.each(commands)('sends exact %s DTO and receipt key to its route',async(operation,body,path,target)=>{
    const fetch=vi.fn().mockResolvedValue(ok(portfolioCommand(operation)));vi.stubGlobal('fetch',fetch);
    await portfolioApi.command(workspace,businessId,operation,body,'original-key','csrf',target);
    expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toBe(prefix+path);expect(fetch.mock.calls[0][1]).toMatchObject({method:'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json','Idempotency-Key':'original-key','X-CSRF-Token':'csrf'},body:JSON.stringify(body)});
  });
  it('enforces UTF8 descriptions/styles, explicit confirmations and required versions before HTTP',()=>{
    const body=commands[3][1];for(const bad of [{...body,description:'я'.repeat(257)},{...body,description:' text '},{...body,attributes:{subject:null,styles:['a','a'],placement:null}},{...body,expected_item_version:null}])expect(()=>validatePortfolioCommand('PORTFOLIO_SAVE',bad as CommandBody)).toThrow();
    expect(()=>validatePortfolioCommand('PORTFOLIO_CONFIRM',{...commands[4][1],confirm_my_work:false}as unknown as CommandBody,{item:itemId})).toThrow();
    expect(()=>validatePortfolioCommand('PORTFOLIO_UPLOAD_FINALIZE',{schema_version:1,expected_asset_version:null}as unknown as CommandBody,uploadTarget)).toThrow();
    expect(()=>validatePortfolioCommand('PORTFOLIO_PUBLISH',{...commands[8][1],knowledge_build_id:assetId}as CommandBody)).toThrow();
    expect(()=>validatePortfolioCommand('PORTFOLIO_DELETE',commands[6][1],{asset:assetId,version:versionId})).toThrow();
  });
  it('reads only, enforces Business/Workspace, and never starts analysis from GET',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(ok(ownerState())).mockResolvedValueOnce(ok({...ownerState(),business_id:assetId}));vi.stubGlobal('fetch',fetch);
    await portfolioApi.state(workspace,businessId);await expect(portfolioApi.state(workspace,businessId)).rejects.toThrow('INVALID_RESPONSE');expect(fetch.mock.calls.every(([,init])=>!init.method&&!init.body)).toBe(true);
  });
  it('sends original File once without manually setting Content-Length or retrying a lost ACK',async()=>{
    const file=new File([new Uint8Array(6000)],'work.png',{type:'image/png'}),fetch=vi.fn().mockRejectedValue(new TypeError('lost ACK'));vi.stubGlobal('fetch',fetch);
    await expect(portfolioApi.upload(workspace,businessId,uploadTarget,file,'csrf')).rejects.toThrow('lost ACK');expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].body).toBe(file);expect(fetch.mock.calls[0][1].method).toBe('PUT');expect(fetch.mock.calls[0][1].headers).toEqual({'Content-Type':'image/png','X-CSRF-Token':'csrf'});
  });
  it('does explicit recovery/purge/analysis/matches without a false receipt key or automatic retry',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(ok({schema_version:1,version_id:versionId,upload_id:uploadId,state:'STORED',recorded:true})).mockResolvedValueOnce(ok({schema_version:1,version_id:versionId,state:'PURGE_PENDING',outcome:'DEPENDENCY_TIMEOUT'})).mockResolvedValueOnce(ok({schema_version:1,outcome:'DISABLED',analysis_id:null,state:null,applied:false})).mockResolvedValueOnce(ok(referenceState())).mockResolvedValueOnce(ok({schema_version:1,outcome:'UNAVAILABLE',analysis_id:null,state:null,applied:false}));vi.stubGlobal('fetch',fetch);
    await portfolioApi.recover(workspace,businessId,uploadTarget,'csrf');await portfolioApi.purge(workspace,businessId,uploadTarget,'csrf');await portfolioApi.analysis(workspace,businessId,uploadTarget,'csrf');await portfolioApi.matches(workspace,businessId,conversationId,clientId,'csrf');await portfolioApi.analysis(workspace,businessId,{conversation:conversationId},'csrf');
    expect(fetch).toHaveBeenCalledTimes(5);for(const [,init]of fetch.mock.calls){expect(init.headers).toEqual({'Content-Type':'application/json','X-CSRF-Token':'csrf'});expect(init.body).toBe('{"schema_version":1}');}
  });
  it('rejects cross-client response, closed errors and invalid preview without a provider call',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(ok({...referenceState(),client_id:assetId})).mockResolvedValueOnce(ok({error:{code:'CLIENT_MODEL_NOT_ALLOWED'}},409)).mockResolvedValueOnce(new Response('bytes',{headers:{'Content-Type':'text/html'}}));vi.stubGlobal('fetch',fetch);
    await expect(portfolioApi.conversation(workspace,businessId,conversationId,clientId)).rejects.toThrow('INVALID_RESPONSE');await expect(portfolioApi.analysis(workspace,businessId,{conversation:conversationId},'csrf')).rejects.toEqual(new PortfolioError(409,'CLIENT_MODEL_NOT_ALLOWED'));await expect(portfolioApi.preview(workspace,businessId,uploadTarget)).rejects.toThrow();expect(fetch).toHaveBeenCalledTimes(3);
  });
});
