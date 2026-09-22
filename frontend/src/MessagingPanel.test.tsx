import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { MessagingPanel } from './MessagingPanel';
import { billingApi } from './billing-api';
import { MessagingError, Message, ReadGrant, SendReceipt, messagingApi } from './messaging-api';
import { connection, conversation, conversationId, deferred, id, message, ok, outbound, page, photo, receipt, session, ws } from './messaging-fixtures.test-helper';

beforeEach(() => {
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
    const old=deferred<ReturnType<typeof page<Message>>>(); vi.mocked(messagingApi.messages).mockImplementationOnce(()=>old.promise).mockResolvedValue(page({...message(90),text:'Current context'}));
    const v=setup(); await waitFor(()=>expect(messagingApi.messages).toHaveBeenCalledTimes(1));
    const next={...session('other'),user_account_id:id(80),memberships:[{...session().memberships[0],workspace_id:id(81)}]};
    v.rerender(<MessagingPanel {...v.props} session={next} workspace={id(81)}/>); await screen.findByText('Current context');
    await act(async()=>{ if(kind==='success')old.resolve(page({...message(),text:'Old private text'}));else old.reject(new MessagingError(Number(kind),kind==='401'?'SESSION_REQUIRED':'ACCESS_DENIED')); });
    expect(screen.queryByText('Old private text')).toBeNull(); expect(screen.getByText('Current context')).toBeVisible(); expect(v.props.expired).not.toHaveBeenCalled(); expect(v.props.recover).not.toHaveBeenCalled();
  });
  it('ignores an old conversation read even after switching back to the same ID', async()=>{
    const old=deferred<ReturnType<typeof page<Message>>>(); vi.mocked(messagingApi.conversations).mockResolvedValue(page(conversation(),conversation(10)));
    vi.mocked(messagingApi.messages).mockImplementationOnce(()=>old.promise).mockResolvedValue(page({...message(90),text:'Fresh projection'})); setup();
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
});
