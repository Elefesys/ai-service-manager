import {act,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach,expect,it,vi} from 'vitest';
import {QuotePanel} from './QuotePanel';
import {SchedulingAvailability} from './SchedulingAvailability';
import {IntakeError,intakeApi} from './intake-api';
import type {QuoteDelivery,ServiceRequestDraft} from './intake-api';
import {availability,bookingView,draft,quoteDelivery,scope,schedulingScope} from './intake-fixtures.test-helper';
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
 vi.spyOn(schedulingApi,'booking').mockImplementation(async selected=>bookingView(selected));
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

it('reloads the saved date after one rejected edit and discards the stale values',async()=>{
 const user=userEvent.setup();
 const initial=availability(schedulingScope,{resource_id:schedulingScope.session,schedule_version:4,
  timezone:'Asia/Novosibirsk',week:[{weekday:3,start_minute:600,end_minute:720}]});
 const saved=availability(schedulingScope,{...initial,schedule_version:5,reason:'DATE_CLOSED',
  exception:{date:initial.date,windows:[]}});
 const preview=vi.spyOn(schedulingApi,'preview').mockResolvedValueOnce(initial).mockResolvedValueOnce(saved);
 const change=vi.spyOn(schedulingApi,'change').mockRejectedValue(new IntakeError(409,'STALE_STATE'));
 render(<SchedulingAvailability scope={schedulingScope} csrf="csrf" expired={vi.fn()}/>);
 await user.click(screen.getByRole('button',{name:'Варианты времени'}));
 await user.click(await screen.findByText('Задать часы на эту дату',{exact:true}));
 const hours=within(screen.getByRole('group',{name:'Часы на выбранную дату'}));
 await user.click(hours.getByRole('button',{name:'Добавить интервал'}));
 await user.type(hours.getByLabelText('Начало'),'10:00');
 await user.type(hours.getByLabelText('Окончание'),'12:30');
 await user.click(hours.getByRole('button',{name:'Сохранить часы на дату'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Проверьте сохранённые значения перед новой правкой.');
 expect(screen.getByText('На эту дату отмечен выходной.',{exact:true})).toBeVisible();
 expect(screen.getByRole('button',{name:'Отметить выходной'})).toBeDisabled();
 expect(screen.queryByRole('list',{name:'Подходящие окна'})).not.toBeInTheDocument();
 await user.click(screen.getByText('Задать часы на эту дату',{exact:true}));
 expect(screen.getByRole('button',{name:'Сохранить часы на дату'})).toBeDisabled();
 expect(change).toHaveBeenCalledExactlyOnceWith(schedulingScope,initial.date,{action:'exception',date:initial.date,
  windows:[{start_minute:600,end_minute:750}],expected_version:4},'csrf',expect.any(AbortSignal));
 expect(preview).toHaveBeenCalledTimes(2);
 expect(preview).toHaveBeenLastCalledWith(schedulingScope,initial.date,expect.any(AbortSignal));
});

it.each([
 [409,'DURATION_UNAVAILABLE','Длительность согласованного сеанса не подтверждена.'],
 [403,'ACCESS_DENIED','Работа недоступна. Откройте список работ заново.'],
 [404,'NOT_FOUND','Работа недоступна. Откройте список работ заново.'],
 [503,'UNAVAILABLE','Не удалось обновить статус предложения.'],
 [401,'AUTH_REQUIRED','Не удалось обновить статус предложения.'],
] as const)('shows the selected work error for %d %s',async(status,code,message)=>{
 const work=draft(),expired=vi.fn();
 const quote=vi.spyOn(intakeApi,'quote').mockRejectedValue(new IntakeError(status,code));
 const preview=vi.spyOn(schedulingApi,'preview');
 render(<QuotePanel scope={scope} draft={work} refresh="" csrf="csrf" approvalChange={null} expired={expired}/>);
 expect((await screen.findByRole('alert')).textContent).toBe(message);
 expect(quote).toHaveBeenCalledExactlyOnceWith(scope,work.request_id,expect.any(AbortSignal));
 expect(screen.queryByRole('button',{name:'Варианты времени'})).not.toBeInTheDocument();
 expect(preview).not.toHaveBeenCalled();
 expect(expired).toHaveBeenCalledTimes(status===401?1:0);
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
