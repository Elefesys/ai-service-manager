import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationControl, ControlIntent } from './ConversationControl';
import { ControlError, ControlReceipt, ControlState, controlApi } from './conversation-control-api';
import { controlBody, controlContext, controlReceipt, controlState, deferred, id, session } from './messaging-fixtures.test-helper';

beforeEach(()=>{
  vi.spyOn(controlApi,'read').mockImplementation(async context=>controlState(context));
  vi.spyOn(controlApi,'command').mockImplementation(async(context,operation,body)=>controlReceipt(operation,body,context));
});
afterEach(()=>vi.restoreAllMocks());
function setup(){
  const intent:{current:ControlIntent|null}={current:null};
  const props={session:session(),context:controlContext(),intent,manualPending:vi.fn(()=>false),refresh:0,accepted:vi.fn(),recover:vi.fn(),expired:vi.fn(),accessDenied:vi.fn()};
  return {...render(<ConversationControl {...props}/>),props,intent};
}
const ready=()=>waitFor(()=>expect(screen.getByRole('button',{name:'Разрешить автоматику'})).toBeEnabled());
const resume=async()=>{await ready();await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Разрешить автоматику'}));});};
const current=()=>screen.findByText('Операция подтверждена. Текущее состояние получено.');

describe('current control and explicit actions',()=>{
  it('mount/refresh are read-only; OWNER role, independent of frozen permissions',async()=>{
    const v=setup();await ready();expect(screen.getByText('Управление у мастера')).toBeVisible();
    fireEvent.click(screen.getByRole('button',{name:'Обновить режим'}));await ready();expect(controlApi.read).toHaveBeenCalledTimes(2);expect(controlApi.command).not.toHaveBeenCalled();
    for(const role of ['ADMIN','PROVIDER'] as const){v.rerender(<ConversationControl {...v.props} session={{...session(),memberships:[{...session().memberships[0],role}]}}/>);expect(screen.queryByRole('region',{name:'Управление диалогом'})).toBeNull();}
    expect(controlApi.read).toHaveBeenCalledTimes(2);expect(localStorage.length+sessionStorage.length).toBe(0);
  });
  it('sends one frozen exact tuple on duplicate clicks, then shows only fresh GET mode',async()=>{
    const pending=deferred<ControlReceipt>();vi.mocked(controlApi.command).mockReturnValue(pending.promise);
    vi.mocked(controlApi.read).mockResolvedValueOnce(controlState()).mockResolvedValue({...controlState(),control_mode:'AI',control_generation:'9007199254740994'});
    const v=setup();await ready();const button=screen.getByRole('button',{name:'Разрешить автоматику'});
    fireEvent.click(button);fireEvent.click(button);expect(controlApi.command).toHaveBeenCalledTimes(1);expect(v.intent.current?.body).toEqual(controlBody());expect(Object.isFrozen(v.intent.current?.body)).toBe(true);
    expect(screen.queryByText('Управление у мастера')).toBeNull();expect(screen.getByRole('button',{name:'Забрать управление'})).toBeDisabled();
    await act(async()=>pending.resolve(controlReceipt()));await current();expect(screen.getByText('Автоматика разрешена')).toBeVisible();expect(v.props.accepted).toHaveBeenCalledTimes(1);expect(v.intent.current).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Забрать управление'}));await waitFor(()=>expect(controlApi.command).toHaveBeenCalledTimes(2));expect(vi.mocked(controlApi.command).mock.calls[1][1]).toBe('TAKEOVER');
  });
  it('confirmed old Resume REPLAY + failed current GET allows only reading; newer HUMAN wins',async()=>{
    vi.mocked(controlApi.command).mockResolvedValue({...controlReceipt(),outcome:'REPLAY'});
    vi.mocked(controlApi.read).mockResolvedValueOnce(controlState()).mockRejectedValueOnce(new TypeError('network')).mockResolvedValue({...controlState(),control_generation:'9007199254740999'});
    setup();await resume();await screen.findByText('Операция подтверждена. Повторяется только чтение режима.');
    expect(screen.queryByText('Автоматика разрешена')).toBeNull();expect(screen.queryByRole('button',{name:'Повторить исходную операцию'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Повторить чтение режима'}));await current();expect(screen.getByText('Управление у мастера')).toBeVisible();expect(controlApi.command).toHaveBeenCalledTimes(1);
  });
  it('STALE reads current state, never retries automatically, next explicit action has new tuple/key',async()=>{
    vi.mocked(controlApi.command).mockRejectedValueOnce(new ControlError(409,'STALE_STATE'));
    vi.mocked(controlApi.read).mockResolvedValueOnce(controlState()).mockResolvedValue({...controlState(),control_generation:'9007199254740997',context_version:'9007199254740998'});
    setup();await resume();await screen.findByText(/Состояние изменилось/);await ready();expect(controlApi.command).toHaveBeenCalledTimes(1);
    await resume();await current();const calls=vi.mocked(controlApi.command).mock.calls;
    expect(calls[0][2]).toEqual(controlBody());expect(calls[1][2]).toEqual({...controlBody(),expected_control_generation:'9007199254740997',expected_context_version:'9007199254740998'});expect(calls[1][3]).not.toBe(calls[0][3]);
  });
  it('fresh manual acceptance signal re-reads without writing CONTROL',async()=>{
    vi.mocked(controlApi.read).mockResolvedValueOnce({...controlState(),control_mode:'AI'}).mockResolvedValue(controlState());
    const v=setup();await ready();v.rerender(<ConversationControl {...v.props} refresh={1}/>);await screen.findByText('Управление у мастера');expect(controlApi.read).toHaveBeenCalledTimes(2);expect(controlApi.command).not.toHaveBeenCalled();
  });
  it('shows both factual delivery warnings without gating takeover or offering resend',async()=>{
    vi.mocked(controlApi.read).mockResolvedValue({...controlState(),manual_delivery:{has_dispatching:true,has_unknown:true}});
    setup();await ready();expect(screen.getByText(/Отправка уже начата/)).toBeVisible();expect(screen.getByText(/Есть отправка с неизвестным результатом/)).toBeVisible();expect(screen.queryByRole('button',{name:/повтор.*отправ/i})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Забрать управление'}));await current();expect(vi.mocked(controlApi.command).mock.calls[0][1]).toBe('TAKEOVER');
  });
  it('server NOT_ALLOWED leaves takeover available after fresh read',async()=>{
    vi.mocked(controlApi.command).mockRejectedValueOnce(new ControlError(409,'NOT_ALLOWED'));setup();await resume();await screen.findByText(/Сервер не разрешил автоматику/);await ready();fireEvent.click(screen.getByRole('button',{name:'Забрать управление'}));await current();expect(controlApi.command).toHaveBeenCalledTimes(2);
  });
});

describe('frozen intent, recovery and context ownership',()=>{
  it.each([new TypeError('network'),new DOMException('Aborted','AbortError'),new ControlError(503,'UNAVAILABLE'),new ControlError(502,'INVALID_RESPONSE')])('ambiguous %s keeps original body/key through new session and fresh tuple',async error=>{
    vi.mocked(controlApi.command).mockRejectedValueOnce(error);const v=setup();await resume();await screen.findByText(/Результат изменения режима неизвестен/);
    const original=vi.mocked(controlApi.command).mock.calls[0];fireEvent.click(screen.getByRole('button',{name:'Проверить сессию для операции'}));expect(v.props.recover).toHaveBeenCalledOnce();
    vi.mocked(controlApi.read).mockResolvedValue({...controlState(),control_generation:'9007199254740999'});
    v.rerender(<ConversationControl {...v.props} session={session('new-csrf')}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходную операцию'})).toBeEnabled());expect(controlApi.command).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Повторить исходную операцию'}));await current();const replay=vi.mocked(controlApi.command).mock.calls[1];expect(replay.slice(0,4)).toEqual(original.slice(0,4));expect(replay[4]).toBe('new-csrf');
  });
  it.each([[401,'SESSION_REQUIRED','expired'],[403,'CSRF_REJECTED','recover']] as const)('current %s uses existing recovery, retaining intent',async(status,code,callback)=>{
    vi.mocked(controlApi.command).mockRejectedValueOnce(new ControlError(status,code));const v=setup();await resume();await waitFor(()=>expect(v.props[callback]).toHaveBeenCalledOnce());const body=v.intent.current?.body;
    v.rerender(<ConversationControl {...v.props} session={null}/>);expect(screen.queryByText('Управление у мастера')).toBeNull();
    v.rerender(<ConversationControl {...v.props} session={session('fresh')}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходную операцию'})).toBeEnabled());expect(v.intent.current?.body).toBe(body);expect(controlApi.command).toHaveBeenCalledTimes(1);
  });
  it('key conflict stops replay; abandoning acknowledges possible server commit',async()=>{
    vi.mocked(controlApi.command).mockRejectedValue(new ControlError(409,'IDEMPOTENCY_KEY_CONFLICT'));const v=setup();await resume();await screen.findByText('Конфликт ключа. Повтор операции остановлен.');expect(screen.queryByRole('button',{name:'Повторить исходную операцию'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Завершить операцию без повтора'}));await ready();expect(v.intent.current).toBeNull();expect(screen.getByText(/Это не отменяет возможную серверную операцию/)).toBeVisible();expect(controlApi.command).toHaveBeenCalledTimes(1);
  });
  it('definitive refusal after ambiguity cannot prove the earlier attempt rolled back',async()=>{
    vi.mocked(controlApi.command).mockRejectedValueOnce(new TypeError('network')).mockRejectedValueOnce(new ControlError(409,'STALE_STATE'));const v=setup();await resume();await screen.findByText(/Результат изменения режима неизвестен/);
    v.rerender(<ConversationControl {...v.props} session={session('new')}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Повторить исходную операцию'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Повторить исходную операцию'}));await screen.findByText(/результат прежней попытки всё ещё неизвестен/);expect(v.intent.current?.body).toEqual(controlBody());
  });
  for(const completion of ['success','401','403'] as const) it.each(['actor','workspace','conversation','session','client'] as const)(`late POST ${completion} cannot affect new %s or authorize another-context replay`,async kind=>{
    const old=deferred<ControlReceipt>();vi.mocked(controlApi.command).mockReturnValue(old.promise);const v=setup();await resume();
    const nextSession=kind==='actor'?{...session(),user_account_id:id(90)}:session('new-session');
    const nextContext=kind==='workspace'?{...controlContext(),workspace:id(91)}:kind==='conversation'?{...controlContext(),conversation:id(92)}:kind==='client'?{...controlContext(),client:id(93)}:controlContext();
    if(kind==='workspace')nextSession.memberships=[{...nextSession.memberships[0],workspace_id:id(91)}];
    v.rerender(<ConversationControl {...v.props} session={nextSession} context={nextContext}/>);await screen.findByText('Управление у мастера');
    await act(async()=>{if(completion==='success')old.resolve(controlReceipt());else old.reject(new ControlError(Number(completion),completion==='401'?'SESSION_REQUIRED':'ACCESS_DENIED'));});expect(v.props.accessDenied).not.toHaveBeenCalled();expect(v.props.expired).not.toHaveBeenCalled();expect(v.props.accepted).not.toHaveBeenCalled();expect(controlApi.command).toHaveBeenCalledTimes(1);
    if(kind!=='session')expect(screen.queryByRole('button',{name:'Повторить исходную операцию'})).toBeNull();
    expect(v.intent.current?.body).toEqual(controlBody());
  });
  it.each(['success','401','403'] as const)('late GET %s after away-and-back cannot change state/session',async kind=>{
    const old=deferred<ControlState>();vi.mocked(controlApi.read).mockReturnValueOnce(old.promise).mockResolvedValue({...controlState(),control_mode:'AI'});const v=setup();await waitFor(()=>expect(controlApi.read).toHaveBeenCalledTimes(1));
    v.rerender(<ConversationControl {...v.props} context={{...controlContext(),conversation:id(80)}}/>);await screen.findByText('Автоматика разрешена');v.rerender(<ConversationControl {...v.props}/>);await ready();
    await act(async()=>{if(kind==='success')old.resolve(controlState());else old.reject(new ControlError(Number(kind),kind==='401'?'SESSION_REQUIRED':'ACCESS_DENIED'));});
    expect(screen.getByText('Автоматика разрешена')).toBeVisible();expect(v.props.expired).not.toHaveBeenCalled();expect(v.props.accessDenied).not.toHaveBeenCalled();
  });
  it('live denial hides current state and notifies the shared owner boundary',async()=>{
    const v=setup();await ready();vi.mocked(controlApi.read).mockRejectedValue(new ControlError(403,'ACCESS_DENIED'));fireEvent.click(screen.getByRole('button',{name:'Обновить режим'}));await waitFor(()=>expect(v.props.accessDenied).toHaveBeenCalledOnce());expect(screen.queryByText('Управление у мастера')).toBeNull();expect(screen.queryByRole('button',{name:'Разрешить автоматику'})).toBeNull();
  });
  it('hard remount performs GET only and never reconstructs a lost intent',async()=>{
    vi.mocked(controlApi.command).mockRejectedValue(new TypeError('network'));const v=setup();await resume();await screen.findByText(/Результат изменения режима неизвестен/);v.unmount();setup();await ready();expect(controlApi.command).toHaveBeenCalledTimes(1);expect(screen.queryByRole('button',{name:'Повторить исходную операцию'})).toBeNull();expect(localStorage.length+sessionStorage.length).toBe(0);
  });
});
