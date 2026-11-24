import {afterEach,expect,it,vi} from 'vitest';
import {availability,schedulingScope as scope} from './intake-fixtures.test-helper';
import {parseAvailability,schedulingApi} from './scheduling-api';

afterEach(()=>vi.unstubAllGlobals());

it('reads the exact accepted session and posts a dated owner exception with CSRF',async()=>{
 const view=availability(),date=view.date;
 const closed=availability(scope,{reason:'DATE_CLOSED',exception:{date,windows:[]}});
 const fetch=vi.fn().mockResolvedValueOnce(Response.json(view)).mockResolvedValueOnce(Response.json(closed));
 vi.stubGlobal('fetch',fetch);
 const {signal}=new AbortController();
 expect(await schedulingApi.preview(scope,date,signal)).toEqual(view);
 const change={action:'exception' as const,date,windows:[],expected_version:view.schedule_version};
 expect(await schedulingApi.change(scope,date,change,'synthetic-csrf',signal)).toEqual(closed);
 const path=`/api/v1/workspaces/${scope.workspace}/businesses/${scope.business}/intake/conversations/${scope.conversation}/service-requests/${scope.request}/sessions/${scope.session}/availability`;
 const query=`client_id=${scope.client}&quote_id=${scope.quote}&order_id=${scope.order}`;
 expect(fetch.mock.calls[0][0]).toBe(`${path}?${query}&date=${date}`);
 expect(fetch.mock.calls[0][1]).toMatchObject({credentials:'include',cache:'no-store'});
 expect(fetch.mock.calls[0][1].method).toBeUndefined();
 expect(fetch.mock.calls[1][0]).toBe(`${path}?${query}`);
 expect(fetch.mock.calls[1][1]).toMatchObject({method:'POST',credentials:'include',headers:{'X-CSRF-Token':'synthetic-csrf','Content-Type':'application/json'}});
 expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual(change);
});

it('preserves the stale-state code only for the matching conflict response',async()=>{
 const view=availability(),{date,schedule_version}=view;
 const fetch=vi.fn()
  .mockResolvedValueOnce(Response.json({error:{code:'STALE_STATE'}},{status:409}))
  .mockResolvedValueOnce(Response.json({error:{code:'NEEDS_CLARIFICATION'}},{status:409}));
 vi.stubGlobal('fetch',fetch);
 const change={action:'exception' as const,date,windows:[],expected_version:schedule_version};
 const send=()=>schedulingApi.change(scope,date,change,'synthetic-csrf',new AbortController().signal);
 await expect(send()).rejects.toMatchObject({status:409,code:'STALE_STATE'});
 await expect(send()).rejects.toMatchObject({status:409,code:'SCHEDULING_REQUEST_FAILED'});
});

it('rejects projections for the wrong work, the wrong date or invalid absolute intervals',()=>{
 const view=availability();
 for(const field of ['request_id','quote_id','order_id','session_id'] as const){
  expect(()=>parseAvailability({...view,[field]:scope.workspace},scope)).toThrow('INVALID_RESPONSE');
 }
 for(const schedule_version of [undefined,1,-1,1.5,Number.MAX_SAFE_INTEGER+1,'0']){
  expect(()=>parseAvailability({...view,schedule_version},scope)).toThrow('INVALID_RESPONSE');
 }
 expect(()=>parseAvailability(view,scope,'2026-11-27')).toThrow('INVALID_RESPONSE');
 expect(()=>parseAvailability({...view,reason:null,windows:[{
  visit_start:`${view.date}T10:15:00+07:00`,visit_end:`${view.date}T11:20:00+07:00`,
  busy_start:`${view.date}T10:05:00+07:00`,busy_end:`${view.date}T10:50:00+07:00`,
 }]},scope)).toThrow('INVALID_RESPONSE');
});
