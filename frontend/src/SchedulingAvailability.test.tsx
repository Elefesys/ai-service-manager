import {act,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach,expect,it,vi} from 'vitest';
import {QuotePanel} from './QuotePanel';
import {SchedulingAvailability} from './SchedulingAvailability';
import {IntakeError,intakeApi} from './intake-api';
import type {QuoteDelivery,ServiceRequestDraft} from './intake-api';
import {availability,draft,quoteDelivery,scope,schedulingScope} from './intake-fixtures.test-helper';
import {schedulingApi} from './scheduling-api';
import type {Availability,SchedulingScope} from './scheduling-api';

afterEach(()=>vi.restoreAllMocks());

function confirmed(card:ServiceRequestDraft,selected:SchedulingScope):QuoteDelivery{
 const delivery=quoteDelivery(card);
 const quote={...delivery.quote,quote_id:selected.quote};
 return {...delivery,quote,agreement:{acceptance_id:selected.order,order_id:selected.order,session_id:selected.session,
  status:'PLANNED',scheduled_at:null,accepted_at:'2026-11-21T13:00:00.000000Z',quote,
  source:{...card.intent_source,status:'AVAILABLE',text:`Принимаю ${quote.code}`}}};
}

it('opens only a chosen agreement and ignores a delayed read after switching work',async()=>{
 const user=userEvent.setup();
 const first=draft();
 const second={...draft(),request_id:'018f0000-0000-7000-8000-000000000030'};
 const secondScope={...schedulingScope,request:second.request_id,quote:'018f0000-0000-7000-8000-000000000031',
  order:'018f0000-0000-7000-8000-000000000032',session:'018f0000-0000-7000-8000-000000000033'};
 vi.spyOn(intakeApi,'quote').mockImplementation(async(_,request)=>request===first.request_id
  ?confirmed(first,schedulingScope):confirmed(second,secondScope));
 let finishFirst!:(view:Availability)=>void;
 const waitFirst=new Promise<Availability>(resolve=>{finishFirst=resolve;});
 const preview=vi.spyOn(schedulingApi,'preview').mockReturnValueOnce(waitFirst)
  .mockResolvedValueOnce(availability(secondScope,{service_name:'Swallow'}));
 const props={scope,refresh:'',approvalChange:null,csrf:'csrf',expired:vi.fn()};
 const view=render(<QuotePanel {...props} draft={first}/>);
 const open=()=>screen.findByRole('button',{name:'Варианты времени'});
 await open();
 expect(preview).not.toHaveBeenCalled();
 await user.click(await open());
 expect(preview).toHaveBeenNthCalledWith(1,schedulingScope,undefined,expect.any(AbortSignal));
 view.rerender(<QuotePanel {...props} draft={second}/>);
 await user.click(await open());
 expect(preview).toHaveBeenNthCalledWith(2,secondScope,undefined,expect.any(AbortSignal));
 expect(preview.mock.calls[0][2].aborted).toBe(true);
 await act(async()=>finishFirst(availability(schedulingScope,{service_name:'Stale flower'})));
 expect(screen.queryByText(/Stale flower/)).not.toBeInTheDocument();
 expect(screen.getByText(/Swallow · 65 мин/)).toBeVisible();
});

it.each([403,404,422])('reports an owner API refusal without showing old windows (%d)',async status=>{
 vi.spyOn(schedulingApi,'preview').mockRejectedValue(new IntakeError(status,'SCHEDULING_REQUEST_FAILED'));
 render(<SchedulingAvailability scope={schedulingScope} csrf="csrf" expired={vi.fn()}/>);
 await userEvent.click(screen.getByRole('button',{name:'Варианты времени'}));
 expect(await screen.findByRole('alert')).toHaveTextContent(status===422?'Проверьте дату и значения настроек.':'Сеанс недоступен.');
 expect(screen.queryByRole('list',{name:'Подходящие окна'})).not.toBeInTheDocument();
});

it('shows two starts with the same clock time and distinct UTC offsets',async()=>{
 const date='2026-11-01';
 vi.spyOn(schedulingApi,'preview').mockResolvedValue(availability(schedulingScope,{
  date,timezone:'America/New_York',reason:null,windows:['-04:00','-05:00'].map(offset=>({
   visit_start:`${date}T01:00:00${offset}`,visit_end:`${date}T01:30:00${offset}`,
   busy_start:`${date}T01:00:00${offset}`,busy_end:`${date}T01:30:00${offset}`,
  })),
 }));
 render(<SchedulingAvailability scope={schedulingScope} csrf="csrf" expired={vi.fn()}/>);
 await userEvent.click(screen.getByRole('button',{name:'Варианты времени'}));
 const list=await screen.findByRole('list',{name:'Подходящие окна'});
 expect(within(list).getAllByRole('listitem').map(item=>item.querySelector('strong')?.textContent)).toEqual([
  'Визит 01:00–01:30 · UTC-04:00','Визит 01:00–01:30 · UTC-05:00',
 ]);
});
