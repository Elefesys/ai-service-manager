import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {randomUUID,webcrypto} from 'node:crypto';
import {act,render,screen,waitFor,cleanup,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {IntakePanel} from './IntakePanel';
import {QuotePanel} from './QuotePanel';
import {intakeApi,IntakeError} from './intake-api';
import type {PriceCalculation,PriceHistory,QuoteDelivery,ServiceRequestDraft} from './intake-api';
import {assessment,draft,intake,scope,session,message,listItem,lateSize,quoteDelivery} from './intake-fixtures.test-helper';
beforeEach(()=>{
 vi.stubGlobal('crypto',{randomUUID,subtle:webcrypto.subtle});
 vi.spyOn(intakeApi,'draft').mockResolvedValue(null);
 vi.spyOn(intakeApi,'drafts').mockResolvedValue([]);
 vi.spyOn(intakeApi,'assessment').mockResolvedValue(null);
 vi.spyOn(intakeApi,'quote').mockResolvedValue({quote:null,status:null,reason:null});
});
afterEach(()=>{cleanup();sessionStorage.clear();vi.restoreAllMocks();vi.unstubAllGlobals();});

it('shows exact versioned terms and keeps a late delivery read out of another request',async()=>{
 const a=draft(),b={...draft(),request_id:message};
 const held=quoteDelivery(a,'HELD','CHANNEL_WINDOW_CLOSED');
 const unknown=quoteDelivery(a,'UNKNOWN','UNKNOWN_EXTERNAL_RESULT');
 let finish!:(value:QuoteDelivery)=>void;
 const read=vi.mocked(intakeApi.quote).mockResolvedValueOnce(held)
  .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}))
  .mockResolvedValueOnce({quote:null,status:'NEEDS_CLARIFICATION',reason:'EXACT_PRICE_REQUIRED'});
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 vi.spyOn(intakeApi,'priceHistory').mockResolvedValue({items:[],next_before_id:null});
 vi.mocked(intakeApi.draft).mockImplementation(async (_scope,id)=>id===b.request_id?b:a);
 vi.mocked(intakeApi.drafts).mockResolvedValue([listItem(a),listItem(b)]);
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);
 const panel=within(await screen.findByRole('region',{name:'Предложение клиенту'}));
 expect(await panel.findByText('Окно ответа в канале закрыто.')).toBeVisible();
 expect(panel.getByRole('status')).toHaveTextContent('Отправка удержана');
 expect(panel.getByTestId('quote-text').textContent).toBe(held.quote.text);
 expect(panel.queryByRole('button',{name:/Отправить/})).not.toBeInTheDocument();
 await userEvent.click(screen.getByRole('button',{name:'Обновить карточку заявки'}));
 await waitFor(()=>expect(read).toHaveBeenCalledTimes(2));
 await userEvent.selectOptions(screen.getByLabelText('Сохранённая заявка'),b.request_id);
 await act(async()=>finish(unknown));
 const selected=within(await screen.findByRole('region',{name:'Предложение клиенту'}));
 expect(await selected.findByText(/Уточните точную цену/)).toBeVisible();
 expect(selected.getByRole('status')).toHaveTextContent('Нужно уточнение');
 expect(selected.queryByTestId('quote-text')).not.toBeInTheDocument();
 expect(read.mock.calls[1][2]?.aborted).toBe(true);
});

it('opens the exact reply from the selected work and cancels navigation when it changes',async()=>{
 const a=draft(),b={...draft(),request_id:message};
 const openMessage=vi.fn<(messageId:string,signal:AbortSignal)=>void>();
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 vi.spyOn(intakeApi,'priceHistory').mockResolvedValue({items:[],next_before_id:null});
 vi.mocked(intakeApi.draft).mockImplementation(async (_scope,id)=>id===b.request_id?b:a);
 vi.mocked(intakeApi.drafts).mockResolvedValue([listItem(a),listItem(b)]);
 vi.mocked(intakeApi.quote).mockResolvedValueOnce({
  ...quoteDelivery(a,'SENT'),reply_notice:{outcome:'DECLINED',message_id:message},
 });
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()} openMessage={openMessage}/>);
 await userEvent.click(await screen.findByRole('link',{name:'Ответ клиента'}));
 expect(openMessage).toHaveBeenCalledExactlyOnceWith(message,expect.any(AbortSignal));
 const signal=openMessage.mock.calls[0][1];
 expect(signal.aborted).toBe(false);
 await userEvent.selectOptions(screen.getByLabelText('Сохранённая заявка'),b.request_id);
 expect(signal.aborted).toBe(true);
 expect(screen.getByTestId('service-request-id')).toHaveTextContent(b.request_id);
});

it.each(['current','previous'] as const)('polls the %s quote through lease expiry and stops at the outcome',async(version)=>{
 vi.useFakeTimers();
 try{
  const a=draft(),{quote}=quoteDelivery(a);
  const clarification={quote:null,status:'NEEDS_CLARIFICATION',reason:'EXACT_PRICE_REQUIRED'} as const;
  const readTimes:number[]=[];
  const openedAt=Date.now();
  const read=vi.mocked(intakeApi.quote).mockImplementation(async()=>{
   const elapsed=Date.now()-openedAt;
   readTimes.push(elapsed);
   const delivery=elapsed<30_000
    ?{quote,status:'DISPATCHING',reason:null} as const
    :{quote,status:'UNKNOWN',reason:'UNKNOWN_EXTERNAL_RESULT'} as const;
   return version==='previous'?{...clarification,previous:delivery}:delivery;
  });
  await act(async()=>{render(<QuotePanel scope={scope} draft={a} refresh="" approvalChange={null} expired={vi.fn()}/>);});
  const card=screen.getByRole('region',{name:'Предложение клиенту'});
  const delivery=within(version==='previous'?within(card).getByRole('region',{name:'Предыдущая версия'}):card);
  const terms=delivery.getByRole('article',{name:'Условия предложения'});
  expect(within(terms).getByText(quote.code,{exact:true})).toBeVisible();
  expect(within(terms).getByTestId('quote-text').textContent).toBe(quote.text);
  if(version==='previous')expect(within(card).getByText(/^Уточните точную цену\./)).toBeVisible();
  await act(async()=>{await vi.advanceTimersByTimeAsync(29_999);});
  expect(delivery.getByRole('status')).toHaveTextContent('Отправка началась, ожидаем подтверждения');
  await act(async()=>{await vi.advanceTimersByTimeAsync(3001);});
  const outcome=delivery.getByRole('status');
  expect(readTimes.at(-1),`Final GET since the card opened (ms). Card at 33000 ms: ${outcome.textContent}`).toBe(30_000);
  expect(outcome).toHaveTextContent('UNKNOWN · Доставка не подтверждена');
  expect(screen.getByRole('region',{name:'Предложение клиенту'})).toBe(card);
  expect(delivery.getByRole('article',{name:'Условия предложения'})).toBe(terms);
  expect(within(terms).getByText(quote.code,{exact:true})).toBeVisible();
  expect(within(terms).getByTestId('quote-text').textContent).toBe(quote.text);
  if(version==='previous')expect(within(card).getByText(/^Уточните точную цену\./)).toBeVisible();
  await act(async()=>{await vi.advanceTimersByTimeAsync(30_000);});
  expect(read).toHaveBeenCalledTimes(16);
  expect(read).toHaveBeenLastCalledWith(scope,a.request_id,expect.any(AbortSignal));
 }finally{vi.useRealTimers();}
});

it('bounds quote polling while the delivery remains queued',async()=>{
 vi.useFakeTimers();
 try{
  const a=draft();
  const read=vi.mocked(intakeApi.quote).mockResolvedValue(quoteDelivery(a,'QUEUED'));
  await act(async()=>{render(<QuotePanel scope={scope} draft={a} refresh="" approvalChange={null} expired={vi.fn()}/>);});
  await act(async()=>{await vi.advanceTimersByTimeAsync(40_000);});
  expect(screen.getByRole('status')).toHaveTextContent('Предложение в очереди на отправку');
  expect(read).toHaveBeenCalledTimes(9);
 }finally{vi.useRealTimers();}
});

it.each([
 ['closing','timer'],['closing','GET'],['switching','timer'],['switching','GET'],
] as const)('cancels quote polling when %s the card with a pending %s',async(change,pending)=>{
 vi.useFakeTimers();
 try{
  const a=draft(),b={...draft(),request_id:message};
  const dispatching=quoteDelivery(a,'DISPATCHING');
  const replacement={quote:null,status:'NEEDS_CLARIFICATION',reason:'EXACT_PRICE_REQUIRED'} as const;
  let finish!:(value:QuoteDelivery)=>void;
  const late=new Promise<QuoteDelivery>(resolve=>{finish=resolve;});
  const read=vi.mocked(intakeApi.quote).mockResolvedValueOnce(dispatching).mockResolvedValue(replacement);
  if(pending==='GET')read.mockReturnValueOnce(late);
  const props={scope,refresh:'',approvalChange:null,expired:vi.fn()};
  const view=render(<QuotePanel {...props} draft={a}/>);
  await act(async()=>{});
  expect(screen.getByRole('status')).toHaveTextContent('Отправка началась, ожидаем подтверждения');
  if(pending==='GET')await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
  const oldCalls=pending==='GET'?2:1;
  expect(read).toHaveBeenCalledTimes(oldCalls);
  const signal=read.mock.lastCall?.[2];
  expect(signal?.aborted).toBe(false);

  if(change==='closing')view.unmount();
  else view.rerender(<QuotePanel {...props} draft={b}/>);
  expect(signal?.aborted).toBe(true);
  await act(async()=>finish(dispatching));
  await act(async()=>{await vi.advanceTimersByTimeAsync(40_000);});

  expect(read.mock.calls.filter(([,id])=>id===a.request_id)).toHaveLength(oldCalls);
  if(change==='switching'){
   expect(read).toHaveBeenCalledTimes(oldCalls+1);
   expect(read).toHaveBeenLastCalledWith(scope,b.request_id,expect.any(AbortSignal));
   expect(screen.getByRole('status')).toHaveTextContent('Нужно уточнение');
  }else{
   expect(read).toHaveBeenCalledTimes(oldCalls);
   expect(screen.queryByRole('region',{name:'Предложение клиенту'})).not.toBeInTheDocument();
  }
  expect(screen.queryByTestId('quote-text')).not.toBeInTheDocument();
 }finally{vi.useRealTimers();}
});

it('shows one missing question, a source link and confirms only the selected field',async()=>{
 const value=intake(),owner=session();vi.spyOn(intakeApi,'summary').mockResolvedValue(value);const command=vi.spyOn(intakeApi,'command').mockResolvedValue({outcome:'ACCEPTED',receipt_id:message,version:'2'});
 render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);expect(await screen.findByText(value.question!)).toBeVisible();expect(screen.getByRole('link',{name:'сообщение клиента'})).toHaveAttribute('href',`#message-${message}`);
 await userEvent.click(screen.getByRole('button',{name:'Подтвердить поле Идея'}));await waitFor(()=>expect(command).toHaveBeenCalledTimes(1));const args=command.mock.calls[0];expect(args[1]).toBe('confirm');expect(args[2]).toEqual({expected_version:'1',expected_fingerprint:value.fingerprint,field:'idea',value:'flower',source:value.facts[0].source});
});
it('hides old facts immediately on auth/scope change and rejects a delayed response',async()=>{
 let resolve!:(v:ReturnType<typeof intake>)=>void;vi.spyOn(intakeApi,'summary').mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValue(intake());const owner=session();const view=render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);
 view.rerender(<IntakePanel session={null} scope={null} expired={vi.fn()}/>);resolve(intake());await waitFor(()=>expect(screen.queryByText('flower')).not.toBeInTheDocument());expect(screen.queryByRole('region',{name:'Предварительный запрос'})).not.toBeInTheDocument();
});
it('removes a stale summary after a version conflict',async()=>{
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());vi.spyOn(intakeApi,'command').mockRejectedValue(new IntakeError(409,'STALE_STATE'));render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);await screen.findByText('Со слов клиента');await userEvent.click(screen.getByRole('button',{name:'Подтвердить поле Идея'}));expect(await screen.findByRole('alert')).toHaveTextContent('Сводка изменилась');expect(screen.queryByLabelText('Идея')).not.toBeInTheDocument();
});
it('keeps owner comparisons scoped to the exact visible summary and hides delayed owner data',async()=>{
 const value=intake(),owner=session();vi.spyOn(intakeApi,'summary').mockResolvedValue(value);
 let finish!:(value:Awaited<ReturnType<typeof intakeApi.search>>)=>void;
 const search=vi.spyOn(intakeApi,'search').mockImplementation(()=>new Promise(r=>{finish=r;}));
 const view=render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);await screen.findByText('Со слов клиента');await userEvent.click(screen.getByRole('button',{name:'Сравнить с примерами мастера'}));
 expect(search).toHaveBeenCalledWith(scope,{},expect.any(AbortSignal));
 view.rerender(<IntakePanel session={null} scope={null} expired={vi.fn()}/>);finish({workspace_id:scope.workspace,business_id:scope.business,items:[]});await waitFor(()=>expect(screen.queryByLabelText('Сравнение примеров мастера')).not.toBeInTheDocument());
});

it('repeats the exact draft command after a lost response and opens and verifies the stored sources',async()=>{
 const value=draft(),owner=session();
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 const read=vi.mocked(intakeApi.draft);
 read.mockResolvedValueOnce(null).mockResolvedValueOnce(value);
 const save=vi.spyOn(intakeApi,'saveDraft').mockRejectedValueOnce(new TypeError('connection lost')).mockResolvedValueOnce({request_id:value.request_id});
 render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);
 await userEvent.selectOptions(await screen.findByLabelText('Начало работы'),message);
 await userEvent.click(screen.getByRole('checkbox',{name:'Идея: flower'}));
 const create=screen.getByRole('button',{name:'Создать заявку'});
 expect(create).toBeDisabled();
 await userEvent.click(screen.getByRole('checkbox',{name:'Начало и выбранные сведения относятся к одной работе'}));
 await userEvent.click(create);
 expect(await screen.findByRole('alert')).toHaveTextContent('Результат создания неизвестен');
 await userEvent.click(screen.getByRole('button',{name:'Повторить создание заявки'}));
 expect(await screen.findByTestId('service-request-id')).toHaveTextContent(value.request_id);
 expect(save).toHaveBeenCalledTimes(2);
 expect(save.mock.calls[1].slice(0,4)).toEqual(save.mock.calls[0].slice(0,4));
 expect(save.mock.calls[0][1]).toEqual({
  expected_version:'1',expected_fingerprint:intake().fingerprint,intent_source:value.intent_source,fields:['idea'],selection:'ONE_WORK',
 });
 expect(read).toHaveBeenLastCalledWith(scope,value.request_id,expect.any(AbortSignal));
 expect(screen.getByRole('link',{name:'Сообщение для поля Идея'})).toHaveAttribute('href',`#message-${message}`);
});

it('keeps the beginning and chosen facts after clarification and creates with a changed selection and new key',async()=>{
 const summary=lateSize(),card=draft();
 summary.facts.unshift(...intake().facts);
 vi.spyOn(intakeApi,'summary').mockResolvedValue(summary);
 vi.mocked(intakeApi.draft).mockResolvedValueOnce(null).mockResolvedValueOnce(card);
 const create=vi.spyOn(intakeApi,'saveDraft').mockRejectedValueOnce(new IntakeError(409,'NEEDS_CLARIFICATION'))
  .mockResolvedValueOnce({request_id:card.request_id});
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);
 const beginning=await screen.findByLabelText('Начало работы');
 await userEvent.selectOptions(beginning,message);
 const idea=screen.getByRole('checkbox',{name:'Идея: flower'});
 const size=screen.getByRole('checkbox',{name:'Примерный размер: 12 cm'});
 const confirmed=screen.getByRole('checkbox',{name:'Начало и выбранные сведения относятся к одной работе'});
 const send=screen.getByRole('button',{name:'Создать заявку'});
 for(const checkbox of [idea,size,confirmed])await userEvent.click(checkbox);
 await userEvent.click(send);

 expect(await screen.findByRole('alert')).toHaveTextContent('Снимите отметку со спорного поля');
 expect(beginning).toHaveValue(message);
 expect(idea).toBeChecked();
 expect(size).toBeChecked();
 expect(confirmed).not.toBeChecked();
 expect(send).toBeDisabled();
 expect(screen.queryByRole('button',{name:'Повторить создание заявки'})).not.toBeInTheDocument();
 await userEvent.click(size);
 await userEvent.click(confirmed);
 await userEvent.click(send);
 expect(await screen.findByTestId('service-request-id')).toHaveTextContent(card.request_id);

 expect(create).toHaveBeenCalledTimes(2);
 const [,original,key]=create.mock.calls[0];
 const [,edited,newKey]=create.mock.calls[1];
 expect(original.fields).toEqual(['idea','approximate_size']);
 expect(edited).toEqual({...original,fields:['idea']});
 expect(newKey).not.toBe(key);
});

it('offers only facts from the selected beginning forward and clears a previous work selection',async()=>{
 const value=intake(),newMessage='018f0000-0000-7000-8000-000000000010',newVersion='e'.repeat(64);
 value.sources.push({message_id:newMessage,source_version:newVersion,text:'another work on the shoulder'});
 value.facts.push({
  ...value.facts[0],field:'placement',value:'shoulder',
  source:{...value.facts[0].source,message_id:newMessage,source_version:newVersion,quote:'shoulder'},
 });
 vi.spyOn(intakeApi,'summary').mockResolvedValue(value);
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);
 const beginning=await screen.findByLabelText('Начало работы');
 await userEvent.selectOptions(beginning,message);
 await userEvent.click(screen.getByRole('checkbox',{name:'Идея: flower'}));
 await userEvent.click(screen.getByRole('checkbox',{name:'Начало и выбранные сведения относятся к одной работе'}));
 await userEvent.selectOptions(beginning,newMessage);
 expect(screen.queryByRole('checkbox',{name:'Идея: flower'})).not.toBeInTheDocument();
 expect(screen.getByRole('checkbox',{name:'Место: shoulder'})).not.toBeChecked();
 expect(screen.getByRole('button',{name:'Создать заявку'})).toBeDisabled();
});

it('suppresses a delayed draft when the client context is replaced',async()=>{
 const owner=session(),value=draft();
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 let finish!:(value:ReturnType<typeof draft>)=>void;
 const read=vi.mocked(intakeApi.draft);
 read.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const view=render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);
 await waitFor(()=>expect(read).toHaveBeenCalledWith(scope,undefined,expect.any(AbortSignal)));
 view.rerender(<IntakePanel session={owner} scope={{...scope,client:value.request_id}} expired={vi.fn()}/>);
 finish(value);
 await waitFor(()=>expect(read).toHaveBeenCalledTimes(2));
 expect(screen.queryByTestId('service-request-id')).not.toBeInTheDocument();
});

it('opens a selected card with GET after reload, retaining the exact scope and revision',async()=>{
 const owner=session(),a=draft(),b={...draft(),request_id:'018f0000-0000-7000-8000-000000000011'};
 b.facts[0].value='swallow';
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 vi.mocked(intakeApi.drafts).mockResolvedValue([listItem(b),listItem(a)]);
 const read=vi.mocked(intakeApi.draft).mockImplementation(async (_scope,id)=>id===a.request_id?a:b);
 const create=vi.spyOn(intakeApi,'saveDraft'),revise=vi.spyOn(intakeApi,'reviseDraft');
 const panel=(session=owner)=><IntakePanel session={session} scope={scope} expired={vi.fn()}/>;
 const first=render(panel());
 const picker=await screen.findByLabelText('Сохранённая заявка');
 await userEvent.selectOptions(picker,a.request_id);
 await waitFor(()=>expect(screen.getByTestId('service-request-id')).toHaveTextContent(a.request_id));
 expect(screen.getByTestId('service-request-revision')).toHaveTextContent('1');
 expect(JSON.stringify(sessionStorage)).toContain(a.request_id);
 expect(JSON.stringify(sessionStorage)).not.toContain(owner.csrf_token);
 first.unmount();
 read.mockClear();

 const reopened=render(panel());
 expect(await screen.findByTestId('service-request-id')).toHaveTextContent(a.request_id);
 expect(read).toHaveBeenCalledExactlyOnceWith(scope,a.request_id,expect.any(AbortSignal));
 expect(screen.getByText(/flower · Со слов клиента/)).toBeVisible();
 expect(screen.getByTestId('service-request-revision')).toHaveTextContent('1');
 reopened.rerender(panel({...owner,csrf_token:'next-session'}));
 expect(screen.queryByTestId('service-request-id')).not.toBeInTheDocument();
 expect(await screen.findByTestId('service-request-id')).toHaveTextContent(b.request_id);
 expect(create).not.toHaveBeenCalled();
 expect(revise).not.toHaveBeenCalled();
});

it('hides the price during summary refresh and discards its read after selecting another request',async()=>{
 const a=draft(),b={...draft(),request_id:'018f0000-0000-7000-8000-000000000011'};
 const price=(card:ServiceRequestDraft,amount:number):PriceCalculation=>({
  calculation_id:card.request_id,request_id:card.request_id,request_revision:card.revision,
  release_id:card.release_id,activation_version:'1',currency:'RUB',current:true,
  policy:null,outcome:'EXACT',authority:'CONFIRMED',reason:'FIXED_PRICE',
  amount_minor:amount,lower_minor:null,upper_minor:null,size_mm:null,steps:null,size_fact:null,
 });
 const first={items:[price(a,350000)],next_before_id:null},second={items:[price(b,400000)],next_before_id:null};
 let finish!:(value:PriceHistory)=>void;
 const priceRead=vi.spyOn(intakeApi,'priceHistory').mockResolvedValueOnce(first)
  .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce(second);
 const calculate=vi.spyOn(intakeApi,'calculatePrice');
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 vi.mocked(intakeApi.drafts).mockResolvedValue([listItem(a),listItem(b)]);
 vi.mocked(intakeApi.draft).mockImplementation(async (_scope,id)=>id===b.request_id?b:a);
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);
 expect(await screen.findByText('3 500 ₽')).toBeVisible();
 await userEvent.click(screen.getByRole('button',{name:'Обновить сводку'}));
 await waitFor(()=>expect(priceRead).toHaveBeenCalledTimes(2));
 const [firstScope,firstId,before,signal]=priceRead.mock.calls[1];
 expect([firstScope,firstId,before]).toEqual([scope,a.request_id,undefined]);
 expect(screen.queryByRole('article',{name:'Текущий расчёт цены'})).not.toBeInTheDocument();
 await userEvent.selectOptions(screen.getByLabelText('Сохранённая заявка'),b.request_id);
 expect(await screen.findByText('4 000 ₽')).toBeVisible();
 expect(signal?.aborted).toBe(true);
 await act(async()=>finish(first));
 expect(screen.getByRole('article',{name:'Текущий расчёт цены'})).toHaveTextContent('4 000 ₽');
 expect(screen.queryByText('3 500 ₽')).not.toBeInTheDocument();
 expect(calculate).not.toHaveBeenCalled();
});

it('uses the chosen late source and loaded revision in an exact replay of one field',async()=>{
 const summary=lateSize(),a=draft(),fact=summary.facts[0];
 const revised={...a,revision:'2',facts:[...a.facts,{...fact,source:{...fact.source,quote:''}}]};
 vi.spyOn(intakeApi,'summary').mockResolvedValue(summary);
 vi.mocked(intakeApi.draft).mockResolvedValueOnce(a).mockResolvedValueOnce(revised);
 vi.mocked(intakeApi.drafts).mockResolvedValue([listItem(a)]);
 const revise=vi.spyOn(intakeApi,'reviseDraft').mockRejectedValueOnce(new TypeError('connection lost')).mockResolvedValueOnce({request_id:a.request_id});
 const create=vi.spyOn(intakeApi,'saveDraft');
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);
 await userEvent.selectOptions(await screen.findByLabelText('Уточняемое сведение'),'approximate_size');
 expect(screen.getByRole('link',{name:'Сообщение для уточнения'})).toHaveAttribute('href',`#message-${fact.source.message_id}`);
 const send=screen.getByRole('button',{name:'Сохранить уточнение заявки'});
 expect(send).toBeDisabled();
 await userEvent.click(screen.getByRole('checkbox',{name:'Сведение из этого сообщения относится к выбранной заявке'}));
 await userEvent.click(send);
 await userEvent.click(await screen.findByRole('button',{name:'Повторить изменение заявки'}));
 await waitFor(()=>expect(screen.getByTestId('service-request-revision')).toHaveTextContent('2'));
 expect(revise.mock.calls[0].slice(0,5)).toEqual(revise.mock.calls[1].slice(0,5));
 expect(revise.mock.calls[0].slice(0,3)).toEqual([scope,a.request_id,{
  expected_revision:'1',expected_version:summary.version,expected_fingerprint:summary.fingerprint,
  field:'approximate_size',source:{message_id:fact.source.message_id,source_version:fact.source.source_version},selection:'ONE_WORK',
 }]);
 expect(screen.getByText(/12 cm · Со слов клиента/)).toBeVisible();
 expect(screen.getByText(/flower · Со слов клиента/)).toBeVisible();
 expect(create).not.toHaveBeenCalled();
});

it('shows archive provenance and exposes minutes only from a current explicitly evaluated result',async()=>{
 const owner=session(),card=draft(),value=assessment();
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 vi.mocked(intakeApi.draft).mockResolvedValue(card);
 vi.mocked(intakeApi.assessment).mockResolvedValue({...value,current:false});
 const evaluate=vi.spyOn(intakeApi,'assess').mockRejectedValueOnce(new TypeError('lost')).mockResolvedValueOnce(value);
 render(<IntakePanel session={owner} scope={scope} expired={vi.fn()}/>);
 const panel=within(await screen.findByRole('region',{name:'Оценка заявки'}));
 expect(await panel.findByText(/Архивная оценка/)).toBeVisible();
 expect(panel.queryByText('65 мин',{exact:true})).not.toBeInTheDocument();
 expect(panel.getByText(value.release_id!,{exact:true})).toBeVisible();
 expect(evaluate).not.toHaveBeenCalled();
 await userEvent.click(panel.getByRole('button',{name:'Пересчитать оценку'}));
 await userEvent.click(await panel.findByRole('button',{name:'Повторить оценку заявки'}));
 expect(await panel.findByText('65 мин',{exact:true})).toBeVisible();
 expect(panel.getByText('Выполнимо',{exact:true})).toBeVisible();
 expect(panel.getByText('Фиксированная длительность из опубликованных настроек.')).toBeVisible();
 expect(panel.getByRole('link',{name:'Источник оценки для поля Идея'})).toHaveAttribute('href',`#message-${message}`);
 expect(evaluate.mock.calls.map(call=>call.slice(0,4))).toEqual([
  [scope,card.request_id,card.revision,owner.csrf_token],[scope,card.request_id,card.revision,owner.csrf_token],
 ]);
});

it('does not display delayed minutes from another selected request in the same conversation',async()=>{
 const a=draft(),b={...draft(),request_id:'018f0000-0000-7000-8000-000000000015'},value=assessment();
 vi.spyOn(intakeApi,'summary').mockResolvedValue(intake());
 vi.mocked(intakeApi.drafts).mockResolvedValue([listItem(a),listItem(b)]);
 vi.mocked(intakeApi.draft).mockImplementation(async (_scope,id)=>id===b.request_id?b:a);
 let finish!:(value:ReturnType<typeof assessment>)=>void;
 vi.mocked(intakeApi.assessment).mockImplementation(async (_scope,id)=>id===a.request_id?new Promise(resolve=>{finish=resolve;}):{
  ...value,request_id:b.request_id,outcome:'NEEDS_DATA',reason:'MISSING_FACT',field:'approximate_size',occupied_minutes:null,evidence:[],
 });
 render(<IntakePanel session={session()} scope={scope} expired={vi.fn()}/>);
 const picker=await screen.findByLabelText('Сохранённая заявка');
 await waitFor(()=>expect(intakeApi.assessment).toHaveBeenCalledWith(scope,a.request_id,expect.any(AbortSignal)));
 await userEvent.selectOptions(picker,b.request_id);
 const panel=within(await screen.findByRole('region',{name:'Оценка заявки'}));
 expect(await panel.findByText('Нужны данные')).toBeVisible();
 finish(value);
 expect(panel.getByText('Какой примерный размер вы представляете, в сантиметрах?')).toBeVisible();
 expect(panel.queryByText('65 мин',{exact:true})).not.toBeInTheDocument();
});
