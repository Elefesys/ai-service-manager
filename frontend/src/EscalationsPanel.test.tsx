import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EscalationsPanel } from './EscalationsPanel';
import { EscalationError, EscalationPage, EscalationReceipt, EscalationView, escalationApi } from './escalation-api';
import { actor, body, context, deferred, escalation, id, observed, page, receipt, session, terminal, workspace } from './escalation-fixtures.test-helper';

beforeEach(()=>{
  vi.spyOn(escalationApi,'list').mockResolvedValue(page(escalation()));
  vi.spyOn(escalationApi,'read').mockResolvedValue(escalation());
  vi.spyOn(escalationApi,'command').mockImplementation(async(c,op,b)=>receipt(op,b,c));
});
afterEach(()=>vi.restoreAllMocks());
function setup(){const props={session:session(),workspace,recover:vi.fn(),expired:vi.fn(),accessDenied:vi.fn(),accepted:vi.fn()};return {...render(<EscalationsPanel {...props}/>),props};}
async function open(n=10){fireEvent.click(await screen.findByTestId(`escalation-${id(n)}`));await screen.findByText('CONTROLLED ESCALATION TEST: требуется решение владельца.');}
const detail=()=>within(screen.getByRole('region',{name:'Карточка запроса'}));
async function submit(answer=body().answer_text!){await open();await act(async()=>{fireEvent.change(screen.getByLabelText('Внутренний ответ владельца'),{target:{value:answer}});const form=screen.getByLabelText('Внутренний ответ владельца').closest('form')!;fireEvent.submit(form);fireEvent.submit(form);});}
const settled=async()=>{await waitFor(()=>expect(screen.queryByText('Читаем актуальный запрос…')).not.toBeInTheDocument());};

describe('owner queue and current projection',()=>{
  it('reads PENDING without a Business/channel/billing prerequisite; chooses explicitly',async()=>{
    setup();await screen.findByTestId(`escalation-${id(10)}`);
    expect(escalationApi.list).toHaveBeenCalledWith(workspace,'PENDING',null,expect.any(AbortSignal));expect(escalationApi.read).not.toHaveBeenCalled();expect(escalationApi.command).not.toHaveBeenCalled();
    await open();expect(escalationApi.read).toHaveBeenCalledWith(context(),expect.any(AbortSignal));expect(detail().getByText('Ожидается решение владельца')).toBeVisible();expect(detail().getByText(/Запись напоминания не означает/)).toBeVisible();
    fireEvent.focus(window);expect(escalationApi.command).not.toHaveBeenCalled();
  });
  it('awaits a specific page, keeps independent page clocks, ends pagination, refreshes and resets filter cursor',async()=>{
    const next=deferred<EscalationPage>(),later={...escalation(11),observed_at:'2030-01-01T00:01:30.123456Z'};
    vi.mocked(escalationApi.list).mockResolvedValueOnce({...page(escalation()),next_cursor:'opaque'}).mockImplementationOnce(()=>next.promise).mockResolvedValue(page());
    setup();const more=await screen.findByRole('button',{name:'Ещё запросы'});fireEvent.click(more);fireEvent.click(more);expect(more).toBeDisabled();expect(escalationApi.list).toHaveBeenCalledTimes(2);
    await act(async()=>{next.resolve(page(later));await next.promise;});await screen.findByTestId(`escalation-${id(11)}`);expect(screen.queryByRole('button',{name:'Ещё запросы'})).not.toBeInTheDocument();expect(screen.getByText(`Наблюдение страницы: ${observed}`)).toBeVisible();expect(screen.getByText(`Наблюдение страницы: ${later.observed_at}`)).toBeVisible();
    fireEvent.click(screen.getByRole('button',{name:'Обновить очередь'}));await screen.findByText('Запросов с этим статусом нет.');
    for(const status of ['ALL','RESOLVED','CANCELLED','EXPIRED','PENDING']){fireEvent.change(screen.getByLabelText('Сохранённый статус'),{target:{value:status}});await waitFor(()=>expect(escalationApi.list).toHaveBeenLastCalledWith(workspace,status,null,expect.any(AbortSignal)));}
    expect(escalationApi.command).not.toHaveBeenCalled();
  });
  it('ignores a late page after filter changed, including old read errors',async()=>{
    const old=deferred<EscalationPage>();vi.mocked(escalationApi.list).mockImplementationOnce(()=>old.promise).mockResolvedValue(page(terminal()));
    const v=setup();fireEvent.change(screen.getByLabelText('Сохранённый статус'),{target:{value:'RESOLVED'}});await screen.findByTestId(`escalation-${id(10)}`);
    await act(async()=>{old.reject(new EscalationError(401,'SESSION_REQUIRED'));await old.promise.catch(()=>{});});expect(v.props.expired).not.toHaveBeenCalled();expect(screen.getByLabelText('Сохранённый статус')).toHaveValue('RESOLVED');
  });
  it.each(['page','detail'] as const)('clears protected %s across Workspace/actor and ignores deferred response',async kind=>{
    const old=deferred<EscalationPage>(),oldDetail=deferred<EscalationView>();
    if(kind==='page')vi.mocked(escalationApi.list).mockImplementationOnce(()=>old.promise);else vi.mocked(escalationApi.read).mockImplementationOnce(()=>oldDetail.promise);
    const v=setup();if(kind==='detail')fireEvent.click(await screen.findByTestId(`escalation-${id(10)}`));
    vi.mocked(escalationApi.list).mockResolvedValue(page());
    v.rerender(<EscalationsPanel {...v.props} workspace={id(99)} session={{...session(),user_account_id:id(98),memberships:[{workspace_id:id(99),role:'OWNER',permissions:[]}]}}/>);
    await screen.findByText('Запросов с этим статусом нет.');await act(async()=>{old.resolve(page(escalation()));oldDetail.resolve(escalation());await Promise.all([old.promise,oldDetail.promise]);});
    expect(screen.queryByTestId(`escalation-${id(10)}`)).not.toBeInTheDocument();expect(screen.queryByText(escalation().question)).not.toBeInTheDocument();expect(v.props.expired).not.toHaveBeenCalled();
  });
  it('drops late detail for a different request with the same actor',async()=>{
    const old=deferred<EscalationView>();vi.mocked(escalationApi.list).mockResolvedValue(page(escalation(),escalation(11)));vi.mocked(escalationApi.read).mockImplementationOnce(()=>old.promise).mockResolvedValue(escalation(11));
    setup();fireEvent.click(await screen.findByTestId(`escalation-${id(10)}`));await open(11);
    await act(async()=>{old.resolve(terminal());await old.promise;});expect(detail().queryByText('Сохранённый внутренний ответ')).not.toBeInTheDocument();expect(detail().getByText(id(111))).toBeInTheDocument();
  });
  it('shows a failed read without keeping the previous detail or enabling its action',async()=>{
    setup();await open();vi.mocked(escalationApi.read).mockRejectedValueOnce(new EscalationError(503,'UNAVAILABLE'));fireEvent.click(screen.getByRole('button',{name:'Обновить запрос'}));
    await screen.findByText('Не удалось прочитать запросы. Повторите чтение.');expect(screen.queryByText(escalation().question)).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'Сохранить внутренний ответ'})).not.toBeInTheDocument();
  });
  it('shows server expiry before timer commit and never infers it from browser time',async()=>{
    const v={...escalation(),validity:'EXPIRED' as const,waiting:null,can_resolve:false,can_cancel:false,observed_at:escalation().expires_at};vi.mocked(escalationApi.read).mockResolvedValue(v);setup();await open();
    expect(detail().getByText('Открытые')).toBeVisible();expect(detail().getByText('Срок истёк')).toBeVisible();expect(detail().getByText('Актуального ожидания нет')).toBeVisible();expect(screen.getByRole('button',{name:'Отменить запрос'})).toBeDisabled();
  });
  it('FAILED maintenance and a recorded internal reminder preserve current owner action',async()=>{
    const v=escalation();v.maintenance='FAILED';v.reminders[0].recorded_at=v.due_at;vi.mocked(escalationApi.read).mockResolvedValue(v);setup();await open();
    expect(detail().getByRole('alert')).toHaveTextContent('Это не завершает запрос');expect(detail().getByText(/записано 2030/)).toBeVisible();expect(detail().getByText('Ожидается решение владельца')).toBeVisible();expect(screen.getByRole('button',{name:'Сохранить внутренний ответ'})).toBeEnabled();
  });
  it('revoked assignee permits another live OWNER cancel, with no answer field',async()=>{
    vi.mocked(escalationApi.read).mockResolvedValue({...escalation(),assignee_user_account_id:id(99),validity:'ASSIGNEE_REVOKED',waiting:null,can_resolve:false});setup();await open();
    expect(screen.getByRole('button',{name:'Сохранить внутренний ответ'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:'Отменить запрос'}));
    await waitFor(()=>expect(escalationApi.command).toHaveBeenCalledTimes(1));expect(vi.mocked(escalationApi.command).mock.calls[0].slice(0,3)).toEqual([context(),'CANCEL',body('CANCEL')]);
  });
  it('does not let a mismatched assignee resolve despite an erroneous action hint',async()=>{
    vi.mocked(escalationApi.read).mockResolvedValue({...escalation(),assignee_user_account_id:id(99)});setup();await open();fireEvent.submit(screen.getByLabelText('Внутренний ответ владельца').closest('form')!);expect(escalationApi.command).not.toHaveBeenCalled();
  });
  it.each(['ADMIN','PROVIDER'] as const)('uses membership role and hides the entire queue for %s',async role=>{
    render(<EscalationsPanel session={{...session(),memberships:[{workspace_id:workspace,role,permissions:['tenancy:read']}]}} workspace={workspace} recover={vi.fn()} expired={vi.fn()} accessDenied={vi.fn()}/>);
    expect(screen.queryByRole('region',{name:'Запросы владельцу'})).not.toBeInTheDocument();expect(escalationApi.list).not.toHaveBeenCalled();
  });
});

describe('immutable decision and recovery',()=>{
  it('captures exact identity/counters/text and synchronously prevents double submit',async()=>{
    const pending=deferred<EscalationReceipt>();vi.mocked(escalationApi.command).mockImplementation(()=>pending.promise);const v=setup();await submit();
    expect(screen.getByText(/Сохраняем решение/)).toBeVisible();expect(escalationApi.command).toHaveBeenCalledTimes(1);const call=vi.mocked(escalationApi.command).mock.calls[0];expect(call.slice(0,3)).toEqual([context(),'RESOLVE',body()]);expect(Object.isFrozen(call[0])).toBe(true);expect(Object.isFrozen(call[2])).toBe(true);
    vi.mocked(escalationApi.read).mockResolvedValue(terminal());vi.mocked(escalationApi.list).mockResolvedValue(page());await act(async()=>{pending.resolve(receipt());await pending.promise;});
    await screen.findByText('Сохранённый внутренний ответ');expect(v.props.accepted).toHaveBeenCalledWith(context());expect(detail().getByText('Актуального ожидания нет')).toBeVisible();expect(document.querySelector('.exact-answer')?.textContent).toBe(body().answer_text);expect(escalationApi.command).toHaveBeenCalledTimes(1);expect(localStorage.length+sessionStorage.length).toBe(0);
  });
  it('does not submit invalid text or trim valid whitespace/Unicode',async()=>{
    setup();await open();for(const value of [' \n','\ud800','x'.repeat(513)]){fireEvent.change(screen.getByLabelText('Внутренний ответ владельца'),{target:{value}});fireEvent.submit(screen.getByLabelText('Внутренний ответ владельца').closest('form')!);}
    expect(escalationApi.command).not.toHaveBeenCalled();expect(screen.getByText(/Введите 1–512/)).toBeVisible();
  });
  it('same actor recovery uses identical body/key through loss and CSRF rejection; never fresh counters',async()=>{
    vi.mocked(escalationApi.command).mockRejectedValueOnce(new TypeError('lost')).mockRejectedValueOnce(new EscalationError(403,'CSRF_REJECTED')).mockResolvedValue({...receipt(),outcome:'REPLAY'});
    const v=setup();await submit();await screen.findByText(/Результат решения неизвестен/);fireEvent.click(screen.getByRole('button',{name:'Проверить сессию для решения'}));expect(v.props.recover).toHaveBeenCalledTimes(1);
    for(const csrf of ['recovered','newest']){
      v.rerender(<EscalationsPanel {...v.props} session={null} workspace=""/>);expect(screen.queryByText(body().answer_text!)).not.toBeInTheDocument();
      vi.mocked(escalationApi.read).mockResolvedValue(terminal());v.rerender(<EscalationsPanel {...v.props} session={session(csrf)}/>);await settled();await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Повторить исходное решение'}));});
      if(csrf==='recovered')await waitFor(()=>expect(v.props.recover).toHaveBeenCalledTimes(2));
    }
    await screen.findByText('Решение сохранено. Актуальная карточка получена.');const calls=vi.mocked(escalationApi.command).mock.calls;expect(calls).toHaveLength(3);expect(calls.map(c=>c[2])).toEqual([body(),body(),body()]);expect(new Set(calls.map(c=>c[3])).size).toBe(1);expect(calls.map(c=>c[4])).toEqual(['csrf','recovered','newest']);
  });
  it('valid200 plus failed detail GET only repeats GET and reads current mode separately',async()=>{
    const v=setup();await open();vi.mocked(escalationApi.read).mockRejectedValueOnce(new EscalationError(503,'UNAVAILABLE')).mockResolvedValue({...terminal(),current_context:{...terminal().current_context,control_mode:'HUMAN',control_generation:'9007199254740999'}});
    fireEvent.change(screen.getByLabelText('Внутренний ответ владельца'),{target:{value:body().answer_text}});fireEvent.submit(screen.getByLabelText('Внутренний ответ владельца').closest('form')!);
    await screen.findByText('Решение подтверждено. Повторяется только чтение.');expect(screen.queryByRole('button',{name:'Повторить исходное решение'})).not.toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Повторить чтение запроса'}));
    await screen.findByText('Управление у мастера');expect(escalationApi.command).toHaveBeenCalledTimes(1);expect(v.props.accepted).toHaveBeenCalledTimes(1);
  });
  it.each(['STALE_STATE','ESCALATION_FINAL','ESCALATION_EXPIRED','IDEMPOTENCY_KEY_CONFLICT'] as const)('stops %s, reads fresh state and requires a new explicit decision',async code=>{
    vi.mocked(escalationApi.command).mockRejectedValueOnce(new EscalationError(409,code));setup();await submit();await screen.findByText(/Повтор решения остановлен/);await settled();
    expect(screen.queryByRole('button',{name:'Повторить исходное решение'})).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Сохранить внутренний ответ'})).toBeDisabled();expect(escalationApi.command).toHaveBeenCalledTimes(1);
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Завершить ожидание решения'}));});await settled();expect(screen.getByRole('button',{name:'Сохранить внутренний ответ'})).toBeEnabled();
  });
  it('a later definitive failure does not erase ambiguity or enable resending with a new key',async()=>{
    vi.mocked(escalationApi.command).mockRejectedValueOnce(new TypeError('lost')).mockRejectedValueOnce(new EscalationError(409,'ESCALATION_FINAL'));
    const v=setup();await submit();await screen.findByText(/Результат решения неизвестен/);v.rerender(<EscalationsPanel {...v.props} session={session('new')}/>);await settled();await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Повторить исходное решение'}));});await screen.findByText(/исходный результат всё ещё неизвестен/);expect(screen.queryByRole('button',{name:'Повторить исходное решение'})).not.toBeInTheDocument();expect(escalationApi.command).toHaveBeenCalledTimes(2);
  });
  it.each(['success','401','403'] as const)('late POST %s cannot populate a different request or change auth',async outcome=>{
    const late=deferred<EscalationReceipt>();vi.mocked(escalationApi.command).mockImplementation(()=>late.promise);vi.mocked(escalationApi.list).mockResolvedValue(page(escalation(),escalation(11)));const v=setup();await submit();vi.mocked(escalationApi.read).mockResolvedValue(escalation(11));await open(11);
    await act(async()=>{if(outcome==='success')late.resolve(receipt());else late.reject(new EscalationError(Number(outcome),outcome==='401'?'SESSION_REQUIRED':'CSRF_REJECTED'));await late.promise.catch(()=>{});});
    expect(v.props.expired).not.toHaveBeenCalled();expect(v.props.recover).not.toHaveBeenCalled();expect(v.props.accepted).not.toHaveBeenCalled();expect(screen.getByRole('region',{name:'Незавершённое решение'})).toBeVisible();expect(screen.queryByText(body().answer_text!)).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Сохранить внутренний ответ'})).toBeDisabled();
  });
  it('another actor sees only a neutral outstanding-intent notice; discard cannot resurrect a late commit',async()=>{
    const late=deferred<EscalationReceipt>();vi.mocked(escalationApi.command).mockImplementation(()=>late.promise);const v=setup();await submit();vi.mocked(escalationApi.list).mockResolvedValue(page());v.rerender(<EscalationsPanel {...v.props} session={{...session(),user_account_id:id(99)}}/>);
    await screen.findByText('Запросов с этим статусом нет.');const notice=screen.getByRole('region',{name:'Незавершённое решение'});expect(notice.textContent).not.toContain(actor);expect(notice.textContent).not.toContain(body().answer_text!);expect(notice.textContent).not.toContain(context().escalation);
    fireEvent.click(screen.getByRole('button',{name:'Завершить ожидание решения'}));await act(async()=>{late.resolve(receipt());await late.promise;});v.rerender(<EscalationsPanel {...v.props} session={session('returned')}/>);await screen.findByText('Запросов с этим статусом нет.');expect(screen.queryByRole('region',{name:'Незавершённое решение'})).not.toBeInTheDocument();expect(escalationApi.command).toHaveBeenCalledTimes(1);
  });
  it.each([[401,'SESSION_REQUIRED','expired'],[403,'CSRF_REJECTED','recover'],[403,'ACCESS_DENIED','accessDenied']] as const)('routes owned command %s/%s to shared auth boundary',async(status,code,callback)=>{
    vi.mocked(escalationApi.command).mockRejectedValueOnce(new EscalationError(status,code));const v=setup();await submit();await waitFor(()=>expect(v.props[callback]).toHaveBeenCalledTimes(1));
    if(callback==='accessDenied')expect(screen.queryByText(escalation().question)).not.toBeInTheDocument();
  });
  it('hard reload loses memory-only intent and never automatically posts',async()=>{
    vi.mocked(escalationApi.command).mockRejectedValueOnce(new TypeError('lost'));const v=setup();await submit();await screen.findByText(/Результат решения неизвестен/);v.unmount();setup();await open();expect(escalationApi.command).toHaveBeenCalledTimes(1);expect(screen.getByLabelText('Внутренний ответ владельца')).toHaveValue('');expect(localStorage.length+sessionStorage.length).toBe(0);
  });
});
