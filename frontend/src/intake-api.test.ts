import {describe,it,expect,vi,afterEach} from 'vitest';
import {parseIntake,parseCases,intakeApi,IntakeError} from './intake-api';
import {intake,scope,example,w,b,c} from './intake-fixtures.test-helper';
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
