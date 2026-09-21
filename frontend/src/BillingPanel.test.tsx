import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BillingPanel } from './BillingPanel';
import { App } from './App';
import { billingApi, BillingError, Billing } from './billing-api';
import { billing, deferred, event, fail, ok, receipt, session, ws } from './billing-fixtures.test-helper';

beforeEach(() => {
  vi.spyOn(billingApi,'read').mockResolvedValue(billing());
  vi.spyOn(billingApi,'audit').mockResolvedValue({items:[],next_cursor:null});
  vi.spyOn(billingApi,'save').mockResolvedValue(receipt());
});
afterEach(() => vi.restoreAllMocks());
const setup = (s = session()) => {
  const recover=vi.fn(), expired=vi.fn();
  const props={session:s, workspace:ws, recover, expired};
  return { ...render(<BillingPanel {...props}/>), props, recover, expired };
};
async function ready() { await waitFor(() => expect(screen.getByRole('button',{name:'Сохранить контакт'})).toBeEnabled()); }
async function submit(name='New contact') { await ready(); fireEvent.change(screen.getByLabelText('Имя контакта'),{target:{value:name}}); await act(async () => { fireEvent.submit(screen.getByRole('button',{name:'Сохранить контакт'}).closest('form')!); }); }

describe('owner panel authority and request ownership', () => {
  it('renders server zero and independent inactive/mode states without disabling administration', async () => {
    const v=setup(); await ready(); expect(screen.getByText('Лимит: 0')).toBeVisible();
    for (const state of [{...billing(),subscription:null,availability:'INACTIVE' as const},{...billing(),mode:'SUSPENDED' as const,mode_active:false}]) {
      vi.mocked(billingApi.read).mockResolvedValue(state); v.rerender(<BillingPanel {...v.props} session={session()}/>); await ready();
      expect(screen.getByTestId('current-contact')).toHaveTextContent('Initial');
      if (!state.subscription) expect(screen.getByText(/текущей подписки нет/)).toBeVisible(); else expect(screen.getByText('SUSPENDED · не действует')).toBeVisible();
    }
  });
  it('hides owner UI for ADMIN/PROVIDER and clears data/controls on live 403', async () => {
    const v=setup(); await ready(); vi.mocked(billingApi.audit).mockRejectedValue(new BillingError(403,'ACCESS_DENIED'));
    fireEvent.click(screen.getByRole('button',{name:'Обновить историю'})); await screen.findByText('Нет доступа к данным владельца'); expect(screen.queryByTestId('current-contact')).not.toBeInTheDocument(); expect(screen.queryByLabelText('Имя контакта')).not.toBeInTheDocument();
    for(const role of ['ADMIN','PROVIDER'] as const) { v.rerender(<BillingPanel {...v.props} session={{...session(),memberships:[{...session().memberships[0],role}]}}/>); expect(screen.queryByRole('region',{name:'Панель владельца'})).not.toBeInTheDocument(); }
  });
  it('keeps structural503 distinct from inactive and from auth loss', async () => {
    vi.mocked(billingApi.read).mockRejectedValue(new BillingError(503,'BILLING_STATE_UNAVAILABLE','BILLING_STATE_MISSING')); const v=setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('BILLING_STATE_MISSING'); expect(screen.queryByText(/текущей подписки нет/)).not.toBeInTheDocument(); expect(v.expired).not.toHaveBeenCalled();
  });
  it('paginates by opaque cursor, stops at null, refreshes and resets Workspace', async () => {
    vi.mocked(billingApi.audit).mockResolvedValueOnce({items:[event()],next_cursor:'opaque_cursor'}).mockResolvedValueOnce({items:[event(2)],next_cursor:null}).mockResolvedValueOnce({items:[],next_cursor:null});
    const v=setup(); fireEvent.click(await screen.findByRole('button',{name:'Загрузить ещё'})); await screen.findByText('Конец истории.'); expect(billingApi.audit).toHaveBeenLastCalledWith(ws,'opaque_cursor',expect.any(AbortSignal)); expect(screen.getAllByText('Контакт изменён')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button',{name:'Обновить историю'})); await screen.findByText('История пуста.');
    v.rerender(<BillingPanel {...v.props} workspace="other"/>); expect(screen.queryByText('Контакт изменён')).not.toBeInTheDocument(); expect(screen.queryByRole('button',{name:'Загрузить ещё'})).not.toBeInTheDocument();
  });
  it('renders mixed Audit labels and preserves pagination for queued manual answers', async () => {
    const contact = event(1);
    const provision = {...event(2),event_type:'WORKSPACE_BILLING_PROVISIONED' as const,object_type:'WORKSPACE_BILLING_ACCOUNT' as const,actor_kind:'LOCAL_PROVISIONER' as const,actor_user_account_id:null,payload:{}};
    const message = {...event(3),event_type:'MESSAGE_SEND_REQUESTED' as const,object_type:'MESSAGE' as const,object_version:'1' as const,actor_kind:'USER_ACCOUNT' as const,actor_user_account_id:session().user_account_id,payload:{content_type:'TEXT' as const}};
    vi.mocked(billingApi.audit).mockResolvedValueOnce({items:[message,contact],next_cursor:'mixed_cursor'}).mockResolvedValueOnce({items:[provision],next_cursor:null});
    setup();
    expect(await screen.findByText('Ручной ответ поставлен в очередь')).toBeVisible();
    expect(screen.getAllByText('Контакт изменён')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button',{name:'Загрузить ещё'}));
    expect(await screen.findByText('Подписка настроена')).toBeVisible();
    expect(screen.getByText('Конец истории.')).toBeVisible();
    expect(billingApi.audit).toHaveBeenLastCalledWith(ws,'mixed_cursor',expect.any(AbortSignal));
  });
  it.each(['success','error'])('ignores late read and Audit %s after actor/Workspace change', async (kind) => {
    const oldRead=deferred<Billing>(), oldAudit=deferred<Awaited<ReturnType<typeof billingApi.audit>>>();
    vi.mocked(billingApi.read).mockImplementationOnce(()=>oldRead.promise).mockResolvedValue({...billing('Other contact'),workspace_id:'other'});
    vi.mocked(billingApi.audit).mockImplementationOnce(()=>oldAudit.promise);
    const v=setup(); const next={...session(),user_account_id:'other-actor',memberships:[{...session().memberships[0],workspace_id:'other'}]};
    v.rerender(<BillingPanel {...v.props} session={next} workspace="other"/>); await ready();
    await act(async()=>{ if(kind==='success'){oldRead.resolve(billing('Late secret')); oldAudit.resolve({items:[event()],next_cursor:'late'});}else{oldRead.reject(new BillingError(401,'SESSION_REQUIRED'));oldAudit.reject(new BillingError(403,'ACCESS_DENIED'));} });
    expect(screen.getByTestId('current-contact')).toHaveTextContent('Other contact'); expect(screen.queryByText('Late secret')).not.toBeInTheDocument(); expect(screen.queryByText('Контакт изменён')).not.toBeInTheDocument(); expect(v.expired).not.toHaveBeenCalled();
  });
  it.each(['UPDATED','NOOP'] as const)('confirms %s only through a subsequent GET; duplicate submit keeps one key',async outcome=>{
    const pending=deferred<ReturnType<typeof receipt>>(); vi.mocked(billingApi.save).mockImplementation(()=>pending.promise); const v=setup(); await submit();
    const form=screen.getByRole('button',{name:'Сохранить контакт'}).closest('form')!; fireEvent.submit(form); fireEvent.submit(form);
    expect(billingApi.save).toHaveBeenCalledTimes(1); expect(screen.getByLabelText('Имя контакта')).toBeDisabled();
    vi.mocked(billingApi.read).mockResolvedValue(billing(outcome==='NOOP'?'Initial':'Current from GET',outcome==='NOOP'?'1':'3'));
    await act(async()=>pending.resolve(receipt(outcome))); await ready(); expect(screen.getByTestId('contact-version')).toHaveTextContent(outcome==='NOOP'?'1':'3'); expect(screen.getByTestId('current-contact')).toHaveTextContent(outcome==='NOOP'?'Initial':'Current from GET'); expect(v.expired).not.toHaveBeenCalled();
  });
  it('retains stale draft separately, requires explicit save with fresh version/key, stops key conflict',async()=>{
    vi.mocked(billingApi.save).mockRejectedValueOnce(new BillingError(409,'STALE_STATE')).mockRejectedValueOnce(new BillingError(409,'IDEMPOTENCY_KEY_CONFLICT'));
    setup(); await ready(); vi.mocked(billingApi.read).mockResolvedValue(billing('Concurrent update','2')); await submit('My draft');
    await screen.findByText(/Конфликт версии/); await ready(); expect(screen.getByLabelText('Имя контакта')).toHaveValue('My draft'); expect(screen.getByTestId('current-contact')).toHaveTextContent('Concurrent update'); expect(billingApi.save).toHaveBeenCalledTimes(1);
    fireEvent.submit(screen.getByRole('button',{name:'Сохранить контакт'}).closest('form')!); await screen.findByText(/Конфликт ключа/);
    const calls=vi.mocked(billingApi.save).mock.calls; expect(calls[0][1].expected_version).toBe('1'); expect(calls[1][1].expected_version).toBe('2'); expect(calls[0][2]).not.toBe(calls[1][2]); expect(screen.getByLabelText('Имя контакта')).toBeDisabled();
  });
  it('PATCH200/GET failure retries GET only and preserves confirmed result',async()=>{
    setup(); await ready(); vi.mocked(billingApi.read).mockRejectedValueOnce(new BillingError(503,'UNAVAILABLE')).mockResolvedValue(billing('Current','2')); await submit();
    await screen.findByText('Команда подтверждена; текущее состояние пока недоступно.'); fireEvent.click(screen.getByRole('button',{name:'Повторить чтение'})); await ready(); expect(billingApi.save).toHaveBeenCalledTimes(1); expect(screen.getByTestId('current-contact')).toHaveTextContent('Current');
  });
  it('preserves command confirmation if the subsequent current read loses permission',async()=>{
    setup(); await ready(); vi.mocked(billingApi.read).mockRejectedValueOnce(new BillingError(403,'ACCESS_DENIED')); await submit();
    await screen.findByText('Нет доступа к данным владельца'); expect(screen.getByText(/Команда в прежнем контексте подтверждена/)).toBeVisible();
    expect(screen.queryByText(/В прежнем контексте осталось сохранение/)).not.toBeInTheDocument(); expect(screen.queryByDisplayValue('New contact')).not.toBeInTheDocument(); expect(billingApi.save).toHaveBeenCalledTimes(1);
  });
  it.each(['success','error'])('detaches a pending save and ignores late %s in another context',async kind=>{
    const pending=deferred<ReturnType<typeof receipt>>(); vi.mocked(billingApi.save).mockImplementation(()=>pending.promise); const v=setup(); await submit('Private draft');
    v.rerender(<BillingPanel {...v.props} session={{...session(),user_account_id:'other'}}/>); await screen.findByText(/В прежнем контексте/);
    await act(async()=>{if(kind==='success')pending.resolve(receipt());else pending.reject(new BillingError(401,'SESSION_REQUIRED'));});
    expect(screen.queryByDisplayValue('Private draft')).not.toBeInTheDocument(); expect(billingApi.save).toHaveBeenCalledTimes(1); expect(v.expired).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Завершить прежнее намерение без повтора'})); await ready(); expect(billingApi.save).toHaveBeenCalledTimes(1);
  });
  it('preserves exact body/key across repeated ambiguity and CSRF recovery, with bounded explicit retry',async()=>{
    vi.mocked(billingApi.save).mockRejectedValueOnce(new TypeError('lost')).mockRejectedValueOnce(new BillingError(403,'CSRF_REJECTED')).mockResolvedValue(receipt());
    const v=setup(); await submit('  Original intent  '); await screen.findByText(/Результат сохранения неизвестен/);
    for(const token of ['new-csrf','newest-csrf']) {
      fireEvent.click(screen.getByRole('button',{name:'Проверить сессию для повтора'})); expect(v.recover).toHaveBeenCalled();
      v.rerender(<BillingPanel {...v.props} session={null} workspace=""/>); vi.mocked(billingApi.read).mockResolvedValue(billing('Server later state','9'));
      v.rerender(<BillingPanel {...v.props} session={session(token)}/>);
      const retry=await screen.findByRole('button',{name:'Повторить исходное сохранение'}); await waitFor(()=>expect(retry).toBeEnabled()); fireEvent.click(retry);
      if(token==='new-csrf') await screen.findByRole('button',{name:'Проверить сессию для повтора'});
    }
    await ready(); const calls=vi.mocked(billingApi.save).mock.calls; expect(calls).toHaveLength(3); expect(calls.map(c=>c[1])).toEqual(Array(3).fill({expected_version:'1',contact_display_name:'  Original intent  '})); expect(new Set(calls.map(c=>c[2])).size).toBe(1); expect(calls.map(c=>c[3])).toEqual(['test-csrf','new-csrf','newest-csrf']);
  });
  it('full Console retains intent across 401/bootstrap/login, focus and does not poll or replay on reload',async()=>{
    let authenticated=true, sessionCount=0;
    vi.stubGlobal('fetch',vi.fn((url: string)=>{
      if(url.endsWith('/auth/session')) {sessionCount++; return Promise.resolve(authenticated?ok(session(`csrf-${sessionCount}`)):fail(401,'SESSION_REQUIRED'));}
      if(url.endsWith('/auth/bootstrap')) return Promise.resolve(ok({csrf_token:'bootstrap',expires_at:'2030-01-01T00:00:00Z'}));
      if(url.endsWith('/auth/login')) {authenticated=true; return Promise.resolve(ok(session('login-csrf')));}
      if(url.endsWith('/businesses')) return Promise.resolve(ok({businesses:[]}));
      throw new Error('Unexpected test path');
    }));
    vi.mocked(billingApi.save).mockRejectedValueOnce(new BillingError(401,'SESSION_REQUIRED')).mockResolvedValue(receipt());
    const v=render(<App/>); await ready(); authenticated=false; await submit('Preserved'); await screen.findByLabelText('Логин');
    fireEvent.change(screen.getByLabelText('Логин'),{target:{value:'owner.test'}}); fireEvent.change(screen.getByLabelText('Пароль'),{target:{value:'long-test-password'}}); fireEvent.submit(screen.getByRole('button',{name:'Войти'}).closest('form')!);
    const retry=await screen.findByRole('button',{name:'Повторить исходное сохранение'}); await waitFor(()=>expect(retry).toBeEnabled()); expect(billingApi.save).toHaveBeenCalledTimes(1);
    fireEvent.focus(window); await waitFor(()=>expect(sessionCount).toBeGreaterThan(1)); const afterFocus=await screen.findByRole('button',{name:'Повторить исходное сохранение'}); await waitFor(()=>expect(afterFocus).toBeEnabled()); fireEvent.click(afterFocus); await ready();
    const calls=vi.mocked(billingApi.save).mock.calls; expect(calls).toHaveLength(2); expect(calls[1][1]).toEqual(calls[0][1]); expect(calls[1][2]).toBe(calls[0][2]);
    v.unmount(); render(<App/>); await ready(); expect(billingApi.save).toHaveBeenCalledTimes(2); expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });
  it('keeps Business and auth usable during billing503 and Ops makes no billing calls',async()=>{
    vi.mocked(billingApi.read).mockRejectedValue(new BillingError(503,'BILLING_STATE_UNAVAILABLE','BILLING_STATE_MISSING'));
    vi.stubGlobal('fetch',vi.fn((url:string)=>Promise.resolve(url.endsWith('/auth/session')?ok(session()):url.endsWith('/businesses')?ok({businesses:[]}):ok({status:'ok',component:'database'}))));
    const v=render(<App/>); await screen.findByText(/BILLING_STATE_MISSING/); expect(screen.getByText('ACTIVE SESSION')).toBeVisible(); expect(screen.getByRole('button',{name:'Выйти'})).toBeEnabled();
    const calls=vi.mocked(billingApi.read).mock.calls.length; v.unmount(); render(<App pathname="/ops/"/>); await screen.findByText('Проверка готовности пройдена'); expect(billingApi.read).toHaveBeenCalledTimes(calls); expect(screen.queryByRole('region',{name:'Audit'})).not.toBeInTheDocument();
  });
});
