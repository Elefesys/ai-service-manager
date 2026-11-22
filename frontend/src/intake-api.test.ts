import {describe,it,expect,vi,afterEach} from 'vitest';
import {parseIntake,parseCases,parseDraft,parseAssessment,parseQuoteDelivery,intakeApi,IntakeError} from './intake-api';
import type {DraftCommand,DraftRevisionCommand} from './intake-api';
import {assessment,draft,intake,scope,example,listItem,quoteDelivery,w,b,c} from './intake-fixtures.test-helper';
afterEach(()=>vi.unstubAllGlobals());
describe('closed intake projections',()=>{
 it('rejects another Client, Workspace and extra owner-only data',()=>{
  expect(parseIntake(intake(),scope).facts[0].value).toBe('flower');
  for(const value of [{...intake(),client_id:c},{...intake(),workspace_id:b},{...intake(),duration_minutes:60}])expect(()=>parseIntake(value,scope)).toThrow(IntakeError);
 });
 it('requires exact source provenance and confirmation actor',()=>{
  const value=intake();value.facts[0].source.source_version='invalid';expect(()=>parseIntake(value,scope)).toThrow();
  const raised=intake();raised.facts[0].status='owner-confirmed';expect(()=>parseIntake(raised,scope)).toThrow();
 });
 it('preserves unknown time and rejects a fake measured zero',()=>{
  const value={workspace_id:w,business_id:b,items:[example()]};expect(parseCases(value,scope).items[0].data.working_minutes).toBeNull();
  value.items[0].data.working_minutes=0;expect(()=>parseCases(value,scope)).toThrow();
 });
 it('sends the exact CAS intent and cookie/CSRF/idempotency boundary',async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({outcome:'ACCEPTED',receipt_id:c,version:'2'}),{status:200}));vi.stubGlobal('fetch',fetch);
  const value=intake(),fact=value.facts[0],body={expected_version:value.version,expected_fingerprint:value.fingerprint,field:fact.field,value:fact.value,source:fact.source};
  await intakeApi.command(scope,'confirm',body,'one-key','one-csrf');const [url,init]=fetch.mock.calls[0];expect(url).toContain(`/intake/conversations/${c}/confirm`);expect(init.credentials).toBe('include');expect(init.headers['X-CSRF-Token']).toBe('one-csrf');expect(init.headers['Idempotency-Key']).toBe('one-key');expect(JSON.parse(init.body)).toEqual(body);
 });
});

it('reads and evaluates just the selected request revision on the assessment endpoint',async()=>{
 const value=assessment(),result=(body:unknown)=>new Response(JSON.stringify(body),{status:200});
 const fetch=vi.fn().mockResolvedValueOnce(result(null)).mockResolvedValueOnce(result(value));
 vi.stubGlobal('fetch',fetch);
 expect(await intakeApi.assessment(scope,value.request_id)).toBeNull();
 expect(await intakeApi.assess(scope,value.request_id,value.request_revision,'csrf')).toEqual(value);
 const url=`/api/v1/workspaces/${w}/businesses/${b}/intake/conversations/${c}/service-requests/${value.request_id}/assessment`;
 expect(fetch.mock.calls.map(call=>call[0])).toEqual([url,url]);
 expect(fetch.mock.calls[0][1]).toMatchObject({credentials:'include',cache:'no-store'});
 expect(fetch.mock.calls[0][1].method).toBeUndefined();
 const write=fetch.mock.calls[1][1];
 expect(write).toMatchObject({method:'POST',credentials:'include',headers:{'X-CSRF-Token':'csrf','Content-Type':'application/json'}});
 expect(write.headers['Idempotency-Key']).toBeUndefined();
 expect(JSON.parse(write.body)).toEqual({expected_revision:value.request_revision});
 expect(()=>parseAssessment(value,c)).toThrow(IntakeError);
 expect(()=>parseAssessment(value,value.request_id,'2')).toThrow(IntakeError);
 expect(()=>parseAssessment({...value,outcome:'NEEDS_DATA'},value.request_id)).toThrow(IntakeError);
});

it('accepts a preceding duration in the same request revision',()=>{
 const value=assessment();
 const archive={
  assessment_id:'018f0000-0000-7000-8000-000000000015',request_revision:value.request_revision,
  release_id:value.release_id,activation_version:value.activation_version,occupied_minutes:65,
 };
 const recalculated={
  ...value,activation_version:'2',occupied_minutes:55,duration_policy:{mode:'FIXED',minutes:55,rule_note:null},
  archived_duration:archive,
 };
 expect(parseAssessment(recalculated,value.request_id,value.request_revision)).toEqual(recalculated);
 for(const invalid of [{...archive,assessment_id:value.assessment_id},{...archive,request_revision:'2'}]){
  expect(()=>parseAssessment({...recalculated,archived_duration:invalid},value.request_id)).toThrow(IntakeError);
 }
});

it('reads the selected quote safely and refuses unrelated conditions or a mismatched command',async()=>{
 const card=draft(),value=quoteDelivery(card);
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(value),{status:200}));
 vi.stubGlobal('fetch',fetch);
 expect(await intakeApi.quote(scope,card.request_id)).toEqual(value);
 const [url,init]=fetch.mock.calls[0];
 expect(url).toBe(`/api/v1/workspaces/${w}/businesses/${b}/intake/conversations/${c}/service-requests/${card.request_id}/quote`);
 expect(init).toMatchObject({credentials:'include',cache:'no-store'});
 expect(init.method).toBeUndefined();
 expect(()=>parseQuoteDelivery(value,scope,c)).toThrow(IntakeError);
 expect(()=>parseQuoteDelivery(value,{...scope,client:c},card.request_id)).toThrow(IntakeError);
 expect(()=>parseQuoteDelivery({...value,quote:{...value.quote,code:'Q-012ABCD235'}},scope,card.request_id)).toThrow(IntakeError);
 expect(()=>parseQuoteDelivery({...value,quote:null},scope,card.request_id)).toThrow(IntakeError);
});

it('checks dispatching and the scope of a previous quote during exact-price clarification',()=>{
 const card=draft(),previous={...quoteDelivery(card),status:'DISPATCHING' as const};
 const clarification={quote:null,status:'NEEDS_CLARIFICATION',reason:'EXACT_PRICE_REQUIRED',previous};
 expect(parseQuoteDelivery(previous,scope,card.request_id)).toEqual(previous);
 expect(parseQuoteDelivery(clarification,scope,card.request_id)).toEqual(clarification);
 expect(()=>parseQuoteDelivery(clarification,{...scope,client:c},card.request_id)).toThrow(IntakeError);
 expect(()=>parseQuoteDelivery({...clarification,reason:'APPROVAL_CLARIFICATION'},scope,card.request_id)).toThrow(IntakeError);
 expect(()=>parseQuoteDelivery({...clarification,previous:{...previous,status:'NEEDS_CLARIFICATION'}},scope,card.request_id)).toThrow(IntakeError);
});

describe('scoped draft requests',()=>{
 it('requires the requested ID and exact conversation scope for a card',()=>{
  const value=draft();
  expect(parseDraft(value,scope,value.request_id)).toEqual(value);
  for(const field of ['workspace_id','business_id','conversation_id','client_id'])
   expect(()=>parseDraft({...value,[field]:value.request_id},scope)).toThrow(IntakeError);
  expect(()=>parseDraft(value,scope,c)).toThrow(IntakeError);
  const source=value.facts[0].source;
  value.facts[0].status='observed';
  expect(()=>parseDraft(value,scope)).toThrow(IntakeError);
  source.analysis_id=b;source.analysis_sha256='f'.repeat(64);
  expect(parseDraft(value,scope).facts[0].source.analysis_id).toBe(b);
 });
 it('sends only the selection and CAS, then reads the specific card',async()=>{
  const value=draft();
  const result=(body:unknown)=>new Response(JSON.stringify(body),{status:200});
  const fetch=vi.fn().mockResolvedValueOnce(result({request_id:value.request_id})).mockResolvedValueOnce(result(value)).mockResolvedValueOnce(result(null));
  vi.stubGlobal('fetch',fetch);
  const body:DraftCommand={expected_version:'1',expected_fingerprint:intake().fingerprint,intent_source:value.intent_source,fields:['idea'],selection:'ONE_WORK'};
  const receipt=await intakeApi.saveDraft(scope,body,'draft-key','draft-csrf');
  expect(await intakeApi.draft(scope,receipt.request_id)).toEqual(value);
  expect(await intakeApi.draft(scope)).toBeNull();
  const url=`/api/v1/workspaces/${w}/businesses/${b}/intake/conversations/${c}/service-requests`;
  const [post,read,latest]=fetch.mock.calls;
  expect(post[0]).toBe(url);
  expect(post[1]).toMatchObject({method:'POST',credentials:'include',headers:{'X-CSRF-Token':'draft-csrf','Idempotency-Key':'draft-key'}});
  expect(JSON.parse(post[1].body)).toEqual(body);
  expect(read[0]).toBe(`${url}?request_id=${value.request_id}`);
  expect(latest[0]).toBe(url);
 });
 it('reads a closed card list and sends the exact one-field PATCH for the selected ID',async()=>{
  const value=draft(),item=listItem(value);
  const result=(body:unknown)=>new Response(JSON.stringify(body),{status:200});
  const fetch=vi.fn().mockResolvedValueOnce(result({items:[item]})).mockResolvedValueOnce(result({request_id:value.request_id}))
   .mockResolvedValueOnce(result({items:[item,item]})).mockResolvedValueOnce(result({request_id:c}));
  vi.stubGlobal('fetch',fetch);
  const body:DraftRevisionCommand={expected_revision:'1',expected_version:'3',expected_fingerprint:intake().fingerprint,
   field:'approximate_size',source:value.intent_source,selection:'ONE_WORK'};
  expect(await intakeApi.drafts(scope)).toEqual([item]);
  expect(await intakeApi.reviseDraft(scope,value.request_id,body,'key','csrf')).toEqual({request_id:value.request_id});
  const url=`/api/v1/workspaces/${w}/businesses/${b}/intake/conversations/${c}/service-requests`;
  const [index,revision]=fetch.mock.calls;
  expect(index[0]).toBe(`${url}/cards`);
  expect(index[1]).toMatchObject({credentials:'include',cache:'no-store'});
  expect(index[1].method).toBeUndefined();
  expect(revision[0]).toBe(`${url}/${value.request_id}`);
  expect(revision[1]).toMatchObject({method:'PATCH',credentials:'include',headers:{'X-CSRF-Token':'csrf','Idempotency-Key':'key'}});
  expect(JSON.parse(revision[1].body)).toEqual(body);
  await expect(intakeApi.drafts(scope)).rejects.toThrow(IntakeError);
  await expect(intakeApi.reviseDraft(scope,value.request_id,body,'key','csrf')).rejects.toThrow(IntakeError);
 });
});
