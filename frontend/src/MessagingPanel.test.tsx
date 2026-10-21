import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { escalationApi, EscalationError } from './escalation-api';
import { api } from './api';
import { controlApi, ControlReceipt } from './conversation-control-api';
import { HumanContextError, HumanContextState, ReconcileReceipt, humanContextApi } from './human-context-api';
import { controlState, controlReceipt } from './messaging-fixtures.test-helper';
import { MessagingPanel } from './MessagingPanel';
import { billingApi, BillingError } from './billing-api';
import { billing } from './billing-fixtures.test-helper';
import { MessagingError, Message, ReadGrant, SendReceipt, messagingApi } from './messaging-api';
import { connection, conversation, conversationId, deferred, id, message, ok, outbound, page, photo, receipt, session, when, ws } from './messaging-fixtures.test-helper';

beforeEach(() => {
  // Retained pre-native scenarios use the accepted legacy OFF_UNUSED projection.
  // No messaging entitlement or control permission is inferred from this state.
  vi.spyOn(humanContextApi,'read').mockImplementation(async c=>({...controlState(c),policy:'OFF_UNUSED',policy_epoch:'0',observation_epoch:'0',ingress_checkpoint:'0',input_state_hash:'a'.repeat(64),input_gap_limit_exceeded:false,has_unsequenced_context_input:false,current_revision:null,review_status:'POLICY_INACTIVE',context_blockers:['POLICY_INACTIVE'],resume_blockers:[],history_truncated:false,coverage_status:'UNCONFIRMED',pending_context_input:false,has_failed_context_input:false,unreviewed_failed_context_input:false,automation_work:{state:'IDLE',reason:null,job_id:null,turn_id:null,observed_at:controlState(c).observed_at}} satisfies HumanContextState));
  vi.spyOn(humanContextApi,'observations').mockResolvedValue({items:[],next_cursor:null,through_epoch:'0',current_epoch:'0',observed_at:when});
  vi.spyOn(humanContextApi,'reconcile');
  vi.spyOn(escalationApi,'list').mockResolvedValue({items:[],next_cursor:null,observed_at:'2030-01-01T00:00:00.000000Z'});
  vi.spyOn(controlApi,'read').mockImplementation(async context=>controlState(context));
  vi.spyOn(controlApi,'command').mockImplementation(async(context,operation,body)=>controlReceipt(operation,body,context));
  vi.spyOn(messagingApi,'connections').mockResolvedValue(page(connection()));
  vi.spyOn(messagingApi,'conversations').mockResolvedValue(page(conversation()));
  vi.spyOn(messagingApi,'messages').mockResolvedValue(page(message()));
  vi.spyOn(messagingApi,'send').mockResolvedValue(receipt());
  vi.spyOn(messagingApi,'grant').mockResolvedValue({ url:'https://files.example/private?sig=opaque', expires_at:'2030-01-01T00:00:00.000000Z' });
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
function setup() {
  const props={session:session(),workspace:ws,recover:vi.fn(),expired:vi.fn()};
  return { ...render(<MessagingPanel {...props}/>), props };
}
const ready = () => waitFor(() => expect(screen.getByRole('button',{name:'Проверить и отправить'})).toBeEnabled());
async function submit(text='  Оригинал\ne\u0301🙂  ') {
  await ready(); fireEvent.change(screen.getByLabelText('Ручной текстовый ответ'),{target:{value:text}});
  await act(async()=>fireEvent.submit(screen.getByRole('button',{name:'Проверить и отправить'}).closest('form')!));
}
const newSession = (v: ReturnType<typeof setup>, token='recovered') => v.rerender(<MessagingPanel {...v.props} session={session(token)}/>);

describe('manual/control intent coordination',()=>{
  it('accepted native save and failed current GET stay in read-only recovery without self-refreshing or CONTROL/send POST',async()=>{
    const legacy=vi.mocked(humanContextApi.read).getMockImplementation()!,c={workspace:ws,conversation:conversationId,client:conversation().client_id};const off=await legacy(c);const on:HumanContextState={...off,policy:'ON',policy_epoch:'1',review_status:'BOOTSTRAP_REQUIRED',context_blockers:['CONTEXT_CONFIRMATION_REQUIRED'],resume_blockers:['CONTEXT_CONFIRMATION_REQUIRED']};vi.mocked(humanContextApi.read).mockResolvedValueOnce(on).mockRejectedValueOnce(new TypeError('read lost')).mockResolvedValue(on);
    vi.mocked(humanContextApi.reconcile).mockImplementation(async(c,b)=>({outcome:'ACCEPTED',result:{workspace_id:c.workspace,conversation_id:c.conversation,client_id:c.client,receipt_id:id(81),revision_id:id(81),revision_no:'1',previous_revision_id:null,audit_event_id:id(82),control_generation:b.expected_control_generation,previous_context_version:b.expected_context_version,accepted_context_version:String(BigInt(b.expected_context_version)+1n),policy_epoch:b.expected_policy_epoch,observation_epoch:b.expected_observation_epoch,reviewed_ingress_checkpoint:b.expected_ingress_checkpoint,reviewed_input_state_hash:b.expected_input_state_hash,disposition:b.disposition,source_media:b.source_media,coverage:'OWNER_ASSERTED_TEXT_ONLY',accepted_at:when}}));
    setup();await screen.findByLabelText('Новый полный контекст');await waitFor(()=>expect(screen.getByRole('button',{name:'Обновить наблюдения'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Новый полный контекст'),{target:{value:'Explicit context'}});fireEvent.click(screen.getByLabelText('Подтверждаю полную замену или отзыв прежнего контекста'));fireEvent.click(screen.getByLabelText('Я сверил доступный контекст и существенные договорённости'));fireEvent.click(screen.getByRole('button',{name:'Сохранить сверенный контекст'}));await screen.findByText('Сохранение подтверждено. Повторяется только чтение.');expect(humanContextApi.read).toHaveBeenCalledTimes(2);expect(humanContextApi.reconcile).toHaveBeenCalledTimes(1);expect(controlApi.command).not.toHaveBeenCalled();expect(messagingApi.send).not.toHaveBeenCalled();
  });
  it('blocks manual and CONTROL while a native reconciliation is unresolved, using synchronous shared refs',async()=>{
    const legacy=vi.mocked(humanContextApi.read).getMockImplementation()!;vi.mocked(humanContextApi.read).mockImplementation(async(c,signal)=>({...await legacy(c,signal),policy:'ON',policy_epoch:'1',review_status:'BOOTSTRAP_REQUIRED',context_blockers:['CONTEXT_CONFIRMATION_REQUIRED'],resume_blockers:['CONTEXT_CONFIRMATION_REQUIRED']}));
    const pending=deferred<ReconcileReceipt>();vi.mocked(humanContextApi.reconcile).mockReturnValueOnce(pending.promise);setup();await ready();await screen.findByLabelText('Новый полный контекст');await waitFor(()=>expect(screen.getByRole('button',{name:'Обновить наблюдения'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Новый полный контекст'),{target:{value:'Complete replacement'}});fireEvent.click(screen.getByLabelText('Подтверждаю полную замену или отзыв прежнего контекста'));fireEvent.click(screen.getByLabelText('Я сверил доступный контекст и существенные договорённости'));fireEvent.click(screen.getByRole('button',{name:'Сохранить сверенный контекст'}));
    fireEvent.submit(screen.getByRole('button',{name:'Проверить и отправить'}).closest('form')!);fireEvent.click(screen.getByRole('button',{name:'Забрать управление'}));expect(messagingApi.send).not.toHaveBeenCalled();expect(controlApi.command).not.toHaveBeenCalled();expect(humanContextApi.reconcile).toHaveBeenCalledTimes(1);expect(screen.getByLabelText('Ручной текстовый ответ')).toBeDisabled();expect(screen.getByRole('button',{name:'Забрать управление'})).toBeDisabled();await act(async()=>pending.reject(new TypeError('lost')));expect(screen.getByRole('button',{name:'Проверить и отправить'})).toBeDisabled();
  });
  it('blocks manual submit synchronously while CONTROL is unresolved',async()=>{
    const pending=deferred<ControlReceipt>();vi.mocked(controlApi.command).mockReturnValue(pending.promise);setup();await ready();
    fireEvent.change(screen.getByLabelText('Ручной текстовый ответ'),{target:{value:'Draft'}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Разрешить автоматику'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button',{name:'Разрешить автоматику'}));
    fireEvent.submit(screen.getByRole('button',{name:'Проверить и отправить'}).closest('form')!);
    expect(messagingApi.send).not.toHaveBeenCalled();expect(screen.getByLabelText('Ручной текстовый ответ')).toBeDisabled();
    await act(async()=>pending.resolve(controlReceipt()));await ready();expect(screen.getByLabelText('Ручной текстовый ответ')).toHaveValue('Draft');
  });
  it('blocks CONTROL during manual recovery and reads HUMAN after valid202 without control POST',async()=>{
    const pending=deferred<SendReceipt>();vi.mocked(messagingApi.send).mockReturnValue(pending.promise);
    vi.mocked(controlApi.read).mockResolvedValueOnce({...controlState(),control_mode:'AI'}).mockResolvedValue(controlState());setup();await screen.findByText('Автоматика разрешена');await submit();
    expect(screen.getByRole('button',{name:'Забрать управление'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:'Забрать управление'}));expect(controlApi.command).not.toHaveBeenCalled();
    await act(async()=>pending.resolve(receipt()));await screen.findByText('Управление у мастера');await ready();expect(controlApi.read).toHaveBeenCalledTimes(2);expect(controlApi.command).not.toHaveBeenCalled();
  });
});

describe('owner conversation view and private reads', () => {
  it('uses OWNER role with frozen permissions and shows safe exact text', async()=>{
    const v=setup(); await ready();
    expect(screen.getByText('CONTROLLED · LOCAL/TEST · Доступно по наблюдению')).toBeVisible();
    const text=screen.getByTestId(`message-${id(6)}`).querySelector('.message-text'); expect(text?.textContent).toBe(message().text); expect(text?.querySelector('script')).toBeNull();
    for(const role of ['ADMIN','PROVIDER'] as const) { v.rerender(<MessagingPanel {...v.props} session={{...session(),memberships:[{...session().memberships[0],role}]}}/>); expect(screen.queryByRole('region',{name:'Переписка'})).toBeNull(); }
  });
  it('renders all connection/file/delivery states without gating on observations or billing', async()=>{
    vi.mocked(messagingApi.connections).mockResolvedValue(page(...(['AVAILABLE','DISABLED','RIGHTS_MISSING','UNVERIFIED','UNAVAILABLE'] as const).map((state,i)=>({...connection(20+i),provider:'TELEGRAM' as const,state}))));
    vi.mocked(messagingApi.messages).mockResolvedValue(page(...(['PENDING','DISPATCHING','SENT','FAILED','UNKNOWN'] as const).map((state,i)=>({...outbound(state),message_id:id(30+i)})), photo('PENDING',50), photo('FAILED',51),photo()));
    setup(); await ready();
    for(const text of ['Доступно по наблюдению','Подключение отключено','Недостаточно прав','Требует проверки','Последняя проверка не удалась','В очереди','Отправка начата','Канал принял','Отправка отклонена','Результат неизвестен — повтора нет']) expect(screen.getAllByText(new RegExp(text)).length).toBeGreaterThan(0);
    expect(screen.getByText('Изображение загружается.')).toBeVisible(); expect(screen.getByText(/Изображение недоступно · INVALID_INPUT/)).toBeVisible();
    expect(screen.getByRole('button',{name:'Открыть изображение'})).toBeEnabled(); expect(screen.queryByRole('button',{name:/resend|отправить повторно/i})).toBeNull();
  });
  it('keeps mixed manual and automated history neutral with every delivery status', async()=>{
    const states=['PENDING','DISPATCHING','SENT','FAILED','UNKNOWN'] as const;
    const rows=states.flatMap((state,i)=>[
      {...outbound(state),message_id:id(130+i),text:`Manual ${state}`,current:{...outbound(state).current,text:`Manual ${state}`}},
      {...outbound(state),message_id:id(140+i),text:`CONTROLLED GUARDS TEST ${state}`,current:{...outbound(state).current,text:`CONTROLLED GUARDS TEST ${state}`}},
    ]);
    vi.mocked(messagingApi.messages).mockResolvedValue(page(message(),...rows));
    setup(); await ready();
    expect(screen.getAllByText('Исходящее')).toHaveLength(10);
    expect(screen.queryByText('Ручной ответ')).toBeNull();
    for(const row of rows) expect(screen.getByTestId(`message-${row.message_id}`)).toHaveTextContent(row.text!);
    expect(screen.getByLabelText('Ручной текстовый ответ')).toBeEnabled();
    expect(messagingApi.send).not.toHaveBeenCalled();
  });
  it('uses opaque pagination, replaces current projections, resets pages on refresh', async()=>{
    vi.mocked(messagingApi.connections).mockResolvedValueOnce({items:[connection()],next_cursor:'connection_cursor'}).mockResolvedValue(page({...connection(),state:'DISABLED'}));
    vi.mocked(messagingApi.conversations).mockResolvedValueOnce({items:[conversation()],next_cursor:'conversation_cursor'}).mockResolvedValue(page(conversation(10)));
    vi.mocked(messagingApi.messages).mockResolvedValueOnce({items:[outbound()],next_cursor:'message_cursor'}).mockResolvedValueOnce(page(outbound('SENT'),message(15))).mockResolvedValue(page(message(16)));
    setup(); await ready();
    fireEvent.click(screen.getByRole('button',{name:'Ещё подключения'})); fireEvent.click(screen.getByRole('button',{name:'Ещё диалоги'})); fireEvent.click(screen.getByRole('button',{name:'Ещё сообщения'}));
    await screen.findByText('Канал принял'); expect(screen.getAllByTestId(`message-${id(6)}`)).toHaveLength(1);
    expect(messagingApi.messages).toHaveBeenLastCalledWith(ws,conversationId,'message_cursor',expect.any(AbortSignal));
    expect(messagingApi.connections).toHaveBeenLastCalledWith(ws,'connection_cursor',expect.any(AbortSignal)); expect(messagingApi.conversations).toHaveBeenLastCalledWith(ws,'conversation_cursor',expect.any(AbortSignal));
    fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'})); await screen.findByTestId(`message-${id(16)}`);
    expect(screen.queryByTestId(`message-${id(6)}`)).toBeNull(); expect(screen.queryByRole('button',{name:'Ещё сообщения'})).toBeNull(); expect(messagingApi.send).not.toHaveBeenCalled();
  });
  it.each(['success','401','403'])('ignores late %s across actor/Workspace/session changes before auth handling', async kind=>{
    const old=deferred<ReturnType<typeof page<Message>>>(); vi.mocked(messagingApi.messages).mockImplementationOnce(()=>old.promise).mockResolvedValue(page(message(90,'Current context')));
    const v=setup(); await waitFor(()=>expect(messagingApi.messages).toHaveBeenCalledTimes(1));
    const next={...session('other'),user_account_id:id(80),memberships:[{...session().memberships[0],workspace_id:id(81)}]};
    v.rerender(<MessagingPanel {...v.props} session={next} workspace={id(81)}/>); await screen.findByText('Current context');
    await act(async()=>{ if(kind==='success')old.resolve(page(message(6,'Old private text')));else old.reject(new MessagingError(Number(kind),kind==='401'?'SESSION_REQUIRED':'ACCESS_DENIED')); });
    expect(screen.queryByText('Old private text')).toBeNull(); expect(screen.getByText('Current context')).toBeVisible(); expect(v.props.expired).not.toHaveBeenCalled(); expect(v.props.recover).not.toHaveBeenCalled();
  });
  it('ignores an old conversation read even after switching back to the same ID', async()=>{
    const old=deferred<ReturnType<typeof page<Message>>>(); vi.mocked(messagingApi.conversations).mockResolvedValue(page(conversation(),conversation(10)));
    vi.mocked(messagingApi.messages).mockImplementationOnce(()=>old.promise).mockResolvedValue(page(message(90,'Fresh projection'))); setup();
    fireEvent.click(await screen.findByTestId(`conversation-${id(10)}`)); await screen.findByText('Fresh projection'); fireEvent.click(screen.getByTestId(`conversation-${conversationId}`)); await ready();
    await act(async()=>old.reject(new MessagingError(403,'ACCESS_DENIED'))); expect(screen.getByText('Fresh projection')).toBeVisible(); expect(screen.queryByText('Нет доступа к переписке')).toBeNull();
  });
  it('clears all protected views on current denial; history was never gated by subscription', async()=>{
    const v=setup(); await ready(); vi.mocked(messagingApi.messages).mockRejectedValue(new MessagingError(403,'ACCESS_DENIED')); fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'}));
    await screen.findByText('Нет доступа к переписке'); expect(screen.queryByLabelText('Ручной текстовый ответ')).toBeNull(); expect(screen.queryByTestId(`message-${id(6)}`)).toBeNull(); fireEvent.click(screen.getByRole('button',{name:'Проверить доступ к переписке'})); expect(v.props.recover).toHaveBeenCalledTimes(1);
  });
  it('opens only an explicit grant, drops URL on expiry/error/context; never re-signs automatically', async()=>{
    vi.mocked(messagingApi.messages).mockResolvedValue(page(photo())); const v=setup(); await ready(); expect(messagingApi.grant).not.toHaveBeenCalled();
    const url='https://files.example/path%2Fphoto?sig=unchanged'; vi.mocked(messagingApi.grant).mockResolvedValue({url,expires_at:new Date(Date.now()+5000).toISOString().replace('Z','000Z')});
    vi.useFakeTimers(); await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'})));
    expect(screen.getByRole('img')).toHaveAttribute('src',url); expect(screen.getByRole('img')).toHaveAttribute('referrerpolicy','no-referrer'); expect(screen.getByRole('img')).toHaveAttribute('crossorigin','anonymous');
    await act(async()=>vi.advanceTimersByTime(5001)); expect(screen.queryByRole('img')).toBeNull(); expect(messagingApi.grant).toHaveBeenCalledTimes(1); vi.useRealTimers();
    vi.mocked(messagingApi.grant).mockResolvedValue({url,expires_at:'2030-01-01T00:00:00.000000Z'}); fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'})); fireEvent.error(await screen.findByRole('img')); expect(screen.queryByRole('img')).toBeNull(); expect(messagingApi.grant).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'})); await screen.findByRole('img'); v.rerender(<MessagingPanel {...v.props} session={null} workspace=""/>); expect(screen.queryByRole('img')).toBeNull(); expect(localStorage.length+sessionStorage.length).toBe(0);
  });
  it.each(['grant','401'])('late private %s cannot reopen data or expire a new session', async kind=>{
    vi.mocked(messagingApi.messages).mockResolvedValue(page(photo())); const old=deferred<ReadGrant>(); vi.mocked(messagingApi.grant).mockImplementation(()=>old.promise); const v=setup(); await ready(); fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'})); newSession(v); await ready();
    await act(async()=>{if(kind==='grant')old.resolve({url:'https://files.example/old?sig=private',expires_at:'2030-01-01T00:00:00.000000Z'});else old.reject(new MessagingError(401,'SESSION_REQUIRED'));}); expect(screen.queryByRole('img')).toBeNull(); expect(v.props.expired).not.toHaveBeenCalled();
  });
});
describe('one frozen intention and receipt-aware recovery',()=>{
  it('blocks pagination during POST and reads a fresh first page after202 without another send',async()=>{
    const accepted=deferred<SendReceipt>();
    const fresh=deferred<ReturnType<typeof page<Message>>>();
    vi.mocked(messagingApi.send).mockImplementationOnce(()=>accepted.promise);
    vi.mocked(messagingApi.messages).mockResolvedValueOnce({items:[message()],next_cursor:'older_cursor'}).mockImplementationOnce(()=>fresh.promise);
    setup(); await submit('Exact pending reply');
    const more=screen.getByRole('button',{name:'Ещё сообщения'});
    expect(more).toBeDisabled(); fireEvent.click(more);
    expect(messagingApi.messages).toHaveBeenCalledTimes(1);
    await act(async()=>accepted.resolve(receipt()));
    expect(messagingApi.messages).toHaveBeenCalledTimes(2);
    expect(messagingApi.messages).toHaveBeenLastCalledWith(ws,conversationId,null,expect.any(AbortSignal));
    expect(screen.getByRole('button',{name:'Проверить и отправить'})).toBeDisabled();
    await act(async()=>fresh.resolve(page({...outbound(),message_id:receipt().message_id,text:'Exact pending reply',current:{...outbound().current,text:'Exact pending reply'}})));
    await ready(); expect(screen.getByTestId(`message-${receipt().message_id}`)).toHaveTextContent('В очереди');
    expect(screen.getByLabelText('Ручной текстовый ответ')).toHaveValue(''); expect(messagingApi.send).toHaveBeenCalledTimes(1);
  });
  it('blocks double submit, freezes exact astral text and uses202 only as intention',async()=>{
    const pending=deferred<SendReceipt>(); vi.mocked(messagingApi.send).mockImplementation(()=>pending.promise); setup(); const text=' 🙂'.repeat(2000)+'\ne\u0301 ';
    await submit(text); const form=screen.getByRole('button',{name:'Проверить и отправить'}).closest('form')!; fireEvent.submit(form);fireEvent.submit(form); expect(messagingApi.send).toHaveBeenCalledTimes(1); expect(vi.mocked(messagingApi.send).mock.calls[0][2].text).toBe(text); expect(Object.isFrozen(vi.mocked(messagingApi.send).mock.calls[0][2])).toBe(true);
    await act(async()=>pending.resolve(receipt())); await ready(); expect(screen.getByText(/Намерение принято. Доставка/)).toBeVisible(); expect(screen.queryByText('Канал принял',{exact:true})).toBeNull(); expect(screen.getByLabelText('Ручной текстовый ответ')).toHaveValue('');
  });
  it('valid202 then failed GET recovers only through reads, including auth recovery',async()=>{
    const v=setup(); await ready(); vi.mocked(messagingApi.messages).mockRejectedValueOnce(new MessagingError(503,'UNAVAILABLE')).mockResolvedValue(page(outbound('UNKNOWN'))); await submit();
    await screen.findByText('Намерение подтверждено. Повторяется только чтение.'); expect(screen.queryByRole('button',{name:'Повторить исходный ответ'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Повторить чтение сообщений'})); await ready(); expect(screen.getByText(/Результат неизвестен — повтора нет/)).toBeVisible(); newSession(v); await ready(); expect(messagingApi.send).toHaveBeenCalledTimes(1);
  });
  it('retains original actor/Workspace/conversation/body/key across loss, CSRF and login recovery',async()=>{
    vi.mocked(messagingApi.send).mockRejectedValueOnce(new TypeError('lost response')).mockRejectedValueOnce(new MessagingError(403,'CSRF_REJECTED')).mockResolvedValue({...receipt(),outcome:'REPLAY'}); const v=setup(); await submit();
    await screen.findByText(/Результат запроса неизвестен/); fireEvent.click(screen.getByRole('button',{name:'Проверить сессию для ответа'})); expect(v.props.recover).toHaveBeenCalledTimes(1);
    v.rerender(<MessagingPanel {...v.props} session={null} workspace=""/>); expect(screen.queryByDisplayValue('  Оригинал\ne\u0301🙂  ')).toBeNull(); newSession(v,'fresh'); await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходный ответ'})).toBeEnabled()); fireEvent.click(screen.getByRole('button',{name:'Повторить исходный ответ'}));
    await waitFor(()=>expect(v.props.recover).toHaveBeenCalledTimes(2)); newSession(v,'freshest'); await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходный ответ'})).toBeEnabled()); fireEvent.click(screen.getByRole('button',{name:'Повторить исходный ответ'})); await ready();
    const calls=vi.mocked(messagingApi.send).mock.calls; expect(calls).toHaveLength(3); for(const c of calls) expect(c.slice(0,4)).toEqual(calls[0].slice(0,4)); expect(calls.map(c=>c[4])).toEqual(['csrf','fresh','freshest']);
  });
  it.each([409,422,429])('a first definitive%s keeps editable draft; after ambiguity it cannot imply rollback',async status=>{
    const error=new MessagingError(status,status===409?'NOT_ALLOWED':status===422?'INVALID_REQUEST':'RATE_LIMITED'); vi.mocked(messagingApi.send).mockRejectedValueOnce(error).mockRejectedValueOnce(new TypeError('lost')).mockRejectedValue(error);
    const v=setup(); await submit('  original  '); await ready(); expect(screen.getByLabelText('Ручной текстовый ответ')).toHaveValue('  original  ');
    await submit('  original  '); await screen.findByText(/Результат запроса неизвестен/); newSession(v); await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходный ответ'})).toBeEnabled()); fireEvent.click(screen.getByRole('button',{name:'Повторить исходный ответ'}));
    await screen.findByText(/результат прежней попытки/); expect(screen.getByLabelText('Ручной текстовый ответ')).toBeDisabled(); expect(vi.mocked(messagingApi.send).mock.calls[2].slice(0,4)).toEqual(vi.mocked(messagingApi.send).mock.calls[1].slice(0,4));
  });
  it('stops key conflict and distinguishes structural503 without unlocking a new send',async()=>{
    vi.mocked(messagingApi.send).mockRejectedValueOnce(new MessagingError(503,'BILLING_STATE_UNAVAILABLE','BILLING_STATE_INVALID')).mockRejectedValueOnce(new MessagingError(409,'IDEMPOTENCY_KEY_CONFLICT')); const v=setup(); await submit();
    await screen.findByText(/BILLING_STATE_INVALID/); newSession(v); await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходный ответ'})).toBeEnabled()); fireEvent.click(screen.getByRole('button',{name:'Повторить исходный ответ'})); await screen.findByText(/Конфликт ключа/); expect(screen.queryByRole('button',{name:'Повторить исходный ответ'})).toBeNull(); fireEvent.click(screen.getByRole('button',{name:'Завершить ответ без повтора'})); await ready(); expect(messagingApi.send).toHaveBeenCalledTimes(2);
  });
  it.each(['success','401'])('late POST%s cannot alter new conversation or new session',async kind=>{
    const old=deferred<SendReceipt>(); vi.mocked(messagingApi.send).mockImplementation(()=>old.promise); vi.mocked(messagingApi.conversations).mockResolvedValue(page(conversation(),conversation(10))); const v=setup(); await submit('Private frozen answer'); fireEvent.click(screen.getByTestId(`conversation-${id(10)}`)); await screen.findByText(/В прежнем контексте/);
    expect(screen.queryByDisplayValue('Private frozen answer')).toBeNull(); await act(async()=>{if(kind==='success')old.resolve(receipt());else old.reject(new MessagingError(401,'SESSION_REQUIRED'));}); expect(v.props.expired).not.toHaveBeenCalled(); expect(screen.queryByText(/Принятие намерения:/)).toBeNull(); expect(messagingApi.send).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Завершить ответ без повтора'})); await ready(); expect(messagingApi.send).toHaveBeenCalledTimes(1);
  });
  it('keyboard Enter remains newline and no UTF16 maxLength blocks valid scalars',async()=>{
    setup(); await ready(); const input=screen.getByLabelText('Ручной текстовый ответ'); expect(input).not.toHaveAttribute('maxlength'); const user=userEvent.setup(); await user.click(input); await user.type(input,'hello{Enter}world'); expect(input).toHaveValue('hello\nworld'); expect(messagingApi.send).not.toHaveBeenCalled(); await user.tab(); expect(screen.getByRole('button',{name:'Проверить и отправить'})).toHaveFocus();
  });
  it('full Console retains intent through401/login/focus, hard reload reads only; Ops stays separate',async()=>{
    vi.spyOn(billingApi,'read').mockRejectedValue(new TypeError('billing independent')); vi.spyOn(billingApi,'audit').mockResolvedValue({items:[],next_cursor:null}); let authenticated=true, checks=0;
    vi.stubGlobal('fetch',vi.fn((url:string)=>{if(url.endsWith('/auth/session')){checks++;return Promise.resolve(ok(authenticated?session(`csrf-${checks}`):{error:{code:'SESSION_REQUIRED'}},authenticated?200:401));}if(url.endsWith('/auth/bootstrap'))return Promise.resolve(ok({csrf_token:'challenge',expires_at:'2030-01-01T00:00:00Z'}));if(url.endsWith('/auth/login')){authenticated=true;return Promise.resolve(ok(session('logged-in')));}if(url.endsWith('/businesses'))return Promise.resolve(ok({businesses:[]}));return Promise.resolve(ok({status:'ok',component:'database'}));}));
    vi.mocked(messagingApi.send).mockRejectedValueOnce(new MessagingError(401,'SESSION_REQUIRED')).mockResolvedValue(receipt()); const v=render(<App/>); await ready(); authenticated=false; await submit('exact retained answer'); await screen.findByLabelText('Логин'); fireEvent.change(screen.getByLabelText('Логин'),{target:{value:'owner.test'}});fireEvent.change(screen.getByLabelText('Пароль'),{target:{value:'long-test-password'}});fireEvent.submit(screen.getByRole('button',{name:'Войти'}).closest('form')!);
    await screen.findByRole('button',{name:'Повторить исходный ответ'}); const before=checks; fireEvent.focus(window); await waitFor(()=>expect(checks).toBeGreaterThan(before)); await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходный ответ'})).toBeEnabled()); fireEvent.click(screen.getByRole('button',{name:'Повторить исходный ответ'})); await ready(); expect(messagingApi.send).toHaveBeenCalledTimes(2);
    v.unmount(); const reloaded=render(<App/>); await ready(); expect(messagingApi.send).toHaveBeenCalledTimes(2); const reads=vi.mocked(messagingApi.connections).mock.calls.length; reloaded.unmount(); render(<App pathname="/ops/"/>); await screen.findByText('Проверка готовности пройдена'); expect(messagingApi.connections).toHaveBeenCalledTimes(reads); expect(screen.queryByRole('region',{name:'Переписка'})).toBeNull(); expect(localStorage.length+sessionStorage.length).toBe(0);
  });
  it.each(['billing','messaging','escalation','human-context'] as const)('current %s OWNER denial hides all owner panels and preserves a pending reply until explicit recovery',async source=>{
    vi.spyOn(api,'session').mockResolvedValue(session()); vi.spyOn(api,'businesses').mockResolvedValue([]);
    vi.spyOn(billingApi,'read').mockResolvedValue({...billing(),workspace_id:ws});
    vi.spyOn(billingApi,'audit').mockResolvedValue({items:[],next_cursor:null});
    vi.mocked(messagingApi.messages).mockResolvedValue(page(message(),photo()));
    const pending=deferred<SendReceipt>(); vi.mocked(messagingApi.send).mockImplementationOnce(()=>pending.promise).mockResolvedValue(receipt());
    render(<App/>); await ready(); await screen.findByTestId('current-contact');
    fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'})); await screen.findByRole('img');
    await submit('Frozen reply through owner denial');
    if(source==='billing') {vi.mocked(billingApi.read).mockRejectedValueOnce(new BillingError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить подписку'}));}
    else if(source==='messaging') {vi.mocked(messagingApi.connections).mockRejectedValueOnce(new MessagingError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить подключения'}));}
    else if(source==='escalation') {vi.mocked(escalationApi.list).mockRejectedValueOnce(new EscalationError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить очередь'}));}
    else {vi.mocked(humanContextApi.read).mockRejectedValueOnce(new HumanContextError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить контекст'}));}
    await screen.findByText('Нет доступа к данным владельца');
    expect(screen.queryByRole('img')).toBeNull(); expect(screen.queryByTestId('current-contact')).toBeNull();
    expect(screen.queryByRole('region',{name:'Переписка'})).toBeNull(); expect(screen.queryByRole('region',{name:'Audit'})).toBeNull();
    expect(screen.queryByRole('region',{name:'Запросы владельцу'})).toBeNull();
    expect(screen.queryByDisplayValue('Frozen reply through owner denial')).toBeNull(); expect(api.session).toHaveBeenCalledTimes(1);
    await act(async()=>pending.resolve(receipt())); // A late202 cannot reopen the denied context.
    expect(screen.queryByRole('img')).toBeNull(); expect(messagingApi.send).toHaveBeenCalledTimes(1);
    vi.mocked(api.session).mockResolvedValue(session('recovered'));
    fireEvent.click(screen.getByRole('button',{name:'Проверить доступ заново'}));
    const replay=await screen.findByRole('button',{name:'Повторить исходный ответ'}); await waitFor(()=>expect(replay).toBeEnabled());
    expect(messagingApi.send).toHaveBeenCalledTimes(1); expect(screen.queryByRole('img')).toBeNull();
    fireEvent.click(replay); await ready(); const calls=vi.mocked(messagingApi.send).mock.calls;
    expect(calls).toHaveLength(2); expect(calls[1].slice(0,4)).toEqual(calls[0].slice(0,4)); expect(calls[1][4]).toBe('recovered');
  });
});

describe('M3 material refresh',()=>{
  it('removes an already displayed original image after material replacement',async()=>{
    const original=photo();vi.mocked(messagingApi.messages).mockResolvedValue(page(original));
    vi.mocked(messagingApi.grant).mockResolvedValue({url:'https://files.example/original?sig=loaded',expires_at:when});
    setup();await ready();fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'}));
    const image=await screen.findByRole('img');fireEvent.load(image);expect(image).toBeVisible();
    vi.mocked(messagingApi.messages).mockResolvedValue(page({...original,version:'2',current:{schema_version:1,state:'VISIBLE',content_type:'PHOTO',text:'replacement',image_availability:'MEDIA_REPLACED_UNAVAILABLE',changed:true}}));
    fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'}));await screen.findByText('replacement');
    expect(screen.queryByRole('img')).toBeNull();expect(screen.queryByRole('button',{name:'Открыть изображение'})).toBeNull();expect(messagingApi.grant).toHaveBeenCalledTimes(1);
  });
  it('ignores a pending late grant after semantic version changes',async()=>{
    const original=photo();vi.mocked(messagingApi.messages).mockResolvedValue(page(original));
    const late=deferred<Awaited<ReturnType<typeof messagingApi.grant>>>();
    vi.mocked(messagingApi.grant).mockImplementationOnce(()=>late.promise);
    setup();await ready();fireEvent.click(screen.getByRole('button',{name:'Открыть изображение'}));
    const changed={...original,version:'2',current:{schema_version:1 as const,state:'VISIBLE' as const,content_type:'PHOTO' as const,text:'new caption',image_availability:'MEDIA_REPLACED_UNAVAILABLE' as const,changed:true}};
    vi.mocked(messagingApi.messages).mockResolvedValue(page(changed));fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'}));
    await screen.findByText('new caption');
    await act(async()=>late.resolve({url:'https://files.example/old?sig=late',expires_at:when}));
    expect(screen.queryByRole('img')).toBeNull();expect(screen.queryByRole('button',{name:'Открыть изображение'})).toBeNull();
    expect(messagingApi.grant).toHaveBeenCalledTimes(1);
  });
  it('replaces original text after edit and shows deleted state after refresh',async()=>{
    vi.mocked(messagingApi.messages).mockResolvedValue(page(message()));setup();await ready();
    vi.mocked(messagingApi.messages).mockResolvedValue(page({...message(),version:'2',current:{...message().current,text:'Edited current',changed:true}}));
    fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'}));await screen.findByText('Edited current');expect(screen.queryByText(message().text!)).toBeNull();
    vi.mocked(messagingApi.messages).mockResolvedValue(page({...message(),version:'3',current:{schema_version:1,state:'DELETED',content_type:null,text:null,image_availability:'HIDDEN',changed:true}}));
    fireEvent.click(screen.getByRole('button',{name:'Обновить сообщения'}));await screen.findByText('Сообщение удалено.');expect(screen.queryByText('Edited current')).toBeNull();
  });
});
