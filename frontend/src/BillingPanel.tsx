import { FormEvent, useEffect, useRef, useState } from 'react';
import { Session } from './api';
import { AuditItem, Billing, billingApi, BillingError, ContactBody, ContactResult, normalizeContact } from './billing-api';

type Intent = { actor: string; workspace: string; account: string; body: ContactBody; key: string; phase: 'sending' | 'uncertain' | 'confirmed' | 'conflict'; failedSession: Session; result?: ContactResult };
type StaleDraft = { actor: string; workspace: string; value: string };
type View = { generation: number; billing: Billing | null; readBusy: boolean; readError: string; draft: string; notice: string; rows: AuditItem[] | null; cursor: string | null; auditBusy: boolean; auditError: string; denied: boolean };
const blank = (generation: number): View => ({ generation, billing: null, readBusy: true, readError: '', draft: '', notice: '', rows: null, cursor: null, auditBusy: true, auditError: '', denied: false });
const unavailable = (e: unknown) => e instanceof BillingError && e.code === 'BILLING_STATE_UNAVAILABLE' ? `Состояние подписки недоступно: ${e.stateReason}.` : e instanceof BillingError && e.code === 'RATE_LIMITED' ? 'Слишком много запросов. Повторите позже.' : 'Не удалось получить данные. Повторите чтение.';
const reasons = { SUBSCRIPTION_INACTIVE: 'Подписка не действует', SERVICE_MODE_INACTIVE: 'Режим не действует', NOT_ENTITLED: 'Не предоставлено', SERVICE_MODE_RESTRICTED: 'Ограничено режимом' };
const staleNotice = 'Конфликт версии. Черновик сохранён. Проверьте текущее состояние и сохраните заново.';

// Mounted for the lifetime of Console, including login/recovery. Secrets and
// frozen intentions live only in this page's memory; reload performs reads only.
export function BillingPanel({ session, workspace, recover, expired }: { session: Session | null; workspace: string; recover: () => void; expired: () => void }) {
  const owner = !!session && !!workspace && session.memberships.some(m => m.workspace_id === workspace && m.role === 'OWNER');
  const scope = useRef({ session, workspace, owner, generation: 0 });
  if (scope.current.session !== session || scope.current.workspace !== workspace || scope.current.owner !== owner) scope.current = { session, workspace, owner, generation: scope.current.generation + 1 };
  const generation = scope.current.generation;
  const [stored, setView] = useState<View>(() => blank(generation));
  const view = stored.generation === generation ? stored : blank(generation);
  const intent = useRef<Intent | null>(null);
  // A definitive stale response ends the old command, but its draft must survive
  // failed reads and same-actor auth recovery until an explicit new save.
  const staleDraft = useRef<StaleDraft | null>(null);
  if (staleDraft.current && session && (staleDraft.current.actor !== session.user_account_id || staleDraft.current.workspace !== workspace || !owner)) staleDraft.current = null;
  const retainedDraft = () => staleDraft.current?.actor === session?.user_account_id && staleDraft.current?.workspace === workspace ? staleDraft.current : null;
  const [, redraw] = useState(0);
  const controllers = useRef(new Set<AbortController>());
  const readSequence = useRef(0), auditSequence = useRef(0);
  const denied = useRef(-1), alive = useRef(true);
  const readInFlight = useRef(false), auditInFlight = useRef(false);
  const current = () => alive.current && generation === scope.current.generation && scope.current.owner && denied.current !== generation;
  const update = (patch: Partial<View>) => { if (current()) setView(v => ({ ...(v.generation === generation ? v : blank(generation)), ...patch })); };
  const refreshIntent = () => redraw(n => n + 1);
  const matching = !!intent.current && intent.current.actor === session?.user_account_id && intent.current.workspace === workspace;
  const newController = () => { const c = new AbortController(); controllers.current.add(c); return c; };
  function authorization(e: unknown): boolean {
    if (!(e instanceof BillingError)) return false;
    if (e.status === 401 && e.code === 'SESSION_REQUIRED') { expired(); return true; }
    if (e.status === 403 && e.code !== 'CSRF_REJECTED') {
      if (intent.current?.phase === 'sending') { intent.current.phase = 'uncertain'; refreshIntent(); }
      denied.current = generation;
      staleDraft.current = null;
      controllers.current.forEach(c => c.abort());
      setView({ ...blank(generation), denied: true, readBusy: false, auditBusy: false });
      return true;
    }
    return false;
  }
  async function read(keepDraft = false) {
    const sequence = ++readSequence.current, c = newController(); readInFlight.current = true;
    update({ readBusy: true, readError: '' });
    try {
      const billing = await billingApi.read(workspace, c.signal);
      if (!current() || sequence !== readSequence.current) return;
      const pending = intent.current;
      const confirmed = pending?.phase === 'confirmed' && pending.actor === session?.user_account_id && pending.workspace === workspace;
      const retained = retainedDraft();
      update({ billing, readBusy: false, ...(retained ? { draft: retained.value, notice: staleNotice } : !keepDraft && (!pending || confirmed) ? { draft: billing.account.contact_display_name } : {}), ...(confirmed ? { notice: pending.result?.outcome === 'NOOP' ? 'Изменений нет. Версия и Audit сохранены.' : 'Сохранение подтверждено. Текущее состояние получено.' } : {}) });
      if (confirmed) { intent.current = null; refreshIntent(); }
    } catch (e) {
      if (!current() || sequence !== readSequence.current) return;
      if (!authorization(e)) update({ billing: null, readBusy: false, readError: unavailable(e) });
    } finally { controllers.current.delete(c); if (generation === scope.current.generation && sequence === readSequence.current) readInFlight.current = false; }
  }
  async function audit(cursor: string | null = null) {
    const sequence = ++auditSequence.current, c = newController(); auditInFlight.current = true;
    update({ auditBusy: true, auditError: '', ...(cursor === null ? { rows: null, cursor: null } : {}) });
    try {
      const page = await billingApi.audit(workspace, cursor, c.signal);
      if (!current() || sequence !== auditSequence.current) return;
      setView(v => ({ ...(v.generation === generation ? v : blank(generation)), auditBusy: false, cursor: page.next_cursor, rows: cursor === null ? page.items : [...(v.rows ?? []), ...page.items.filter(item => !v.rows?.some(old => old.audit_event_id === item.audit_event_id))] }));
    } catch (e) {
      if (!current() || sequence !== auditSequence.current) return;
      if (!authorization(e)) update({ auditBusy: false, auditError: unavailable(e) });
    } finally { controllers.current.delete(c); if (generation === scope.current.generation && sequence === auditSequence.current) auditInFlight.current = false; }
  }
  useEffect(() => {
    alive.current = true;
    const retained = retainedDraft();
    setView({ ...blank(generation), ...(retained ? { draft: retained.value, notice: staleNotice } : {}) });
    readInFlight.current = false; auditInFlight.current = false;
    if (intent.current?.phase === 'sending') { intent.current.phase = 'uncertain'; refreshIntent(); }
    if (owner) { void read(); void audit(); }
    return () => { alive.current = false; controllers.current.forEach(c => c.abort()); controllers.current.clear(); };
  }, [generation]);

  async function send(pending: Intent) {
    if (!session || !current() || pending.actor !== session.user_account_id || pending.workspace !== workspace || pending.phase === 'sending') return;
    pending.phase = 'sending'; pending.failedSession = session; refreshIntent(); update({ notice: '' });
    const c = newController();
    try {
      const result = await billingApi.save(workspace, pending.body, pending.key, session.csrf_token, c.signal);
      if (!current() || intent.current !== pending) return;
      if (result.billing_account_id !== pending.account) throw new BillingError(502, 'INVALID_RESPONSE');
      pending.phase = 'confirmed'; pending.result = result; refreshIntent();
      update({ notice: 'Команда подтверждена. Уточняем текущее состояние…' });
      await read();
      if (current()) void audit();
    } catch (e) {
      if (!current() || intent.current !== pending) return;
      pending.phase = 'uncertain'; pending.failedSession = session; refreshIntent();
      if (authorization(e)) return;
      if (e instanceof BillingError && e.code === 'STALE_STATE') {
        staleDraft.current = { actor: pending.actor, workspace: pending.workspace, value: pending.body.contact_display_name };
        intent.current = null; refreshIntent();
        update({ draft: pending.body.contact_display_name, notice: staleNotice });
        await read(true);
      } else if (e instanceof BillingError && e.code === 'IDEMPOTENCY_KEY_CONFLICT') {
        pending.phase = 'conflict'; refreshIntent(); update({ notice: 'Конфликт ключа операции. Автоматический повтор остановлен.' });
      } else if (e instanceof BillingError && [404, 413, 415, 422, 429].includes(e.status)) {
        // A prior ambiguous attempt still cannot be declared rolled back.
        update({ notice: 'Сервер отклонил эту попытку. Ранее отправленное сохранение может быть выполнено.' });
      }
    } finally { controllers.current.delete(c); }
  }
  function editDraft(value: string) {
    if (!current()) return;
    const retained = retainedDraft();
    if (retained) retained.value = value;
    update({ draft: value });
  }
  function save(event: FormEvent) {
    event.preventDefault();
    if (!current() || !session || intent.current || !view.billing || readInFlight.current) return;
    try {
      normalizeContact(view.draft);
      // Preserve the EXACT original wire body, including allowed padding.
      const pending: Intent = { actor: session.user_account_id, workspace, account: view.billing.account.billing_account_id, body: Object.freeze({ expected_version: view.billing.account.version, contact_display_name: view.draft }), key: crypto.randomUUID(), phase: 'uncertain', failedSession: session };
      staleDraft.current = null;
      intent.current = pending; void send(pending);
    } catch { update({ notice: 'Введите имя: 1–200 символов Unicode без управляющих символов.' }); }
  }
  function discard() {
    if (intent.current?.phase === 'sending' && matching) return;
    const confirmed = intent.current?.phase === 'confirmed';
    intent.current = null; refreshIntent();
    update({ notice: confirmed ? 'Подтверждённое намерение завершено без повторной записи.' : 'Намерение завершено без повтора. Его результат мог остаться неизвестным.' });
    if (current()) void read();
  }
  const pending = intent.current;
  const detached = pending && (!matching || !owner || view.denied);
  return <>
    {detached && <section className="panel alert" aria-label="Незавершённое сохранение"><p role="status">{pending.phase === 'confirmed' ? 'Команда в прежнем контексте подтверждена; текущее состояние недоступно. Повторной записи не будет.' : 'В прежнем контексте осталось сохранение с неподтверждённым результатом. Оно не будет перенесено или повторено в этом контексте.'}</p><button className="secondary" onClick={discard}>Завершить прежнее намерение без повтора</button></section>}
    {owner && (view.denied ? <section className="panel alert" role="alert"><h2>Нет доступа к данным владельца</h2><p>Защищённые данные скрыты.</p><button onClick={recover}>Проверить доступ заново</button></section> : <section className="panel billing" aria-label="Панель владельца">
      <div className="billing-heading"><div><span className="kicker">OWNER · LOCAL / TEST</span><h2>Подписка и возможности</h2></div><button className="secondary" disabled={view.readBusy || pending?.phase === 'sending'} onClick={() => { if (!readInFlight.current) void read(!!pending); }}>Обновить подписку</button></div>
      {view.readBusy && <p role="status">Загружаем подписку…</p>}
      {view.readError && <p role="alert">{view.readError}</p>}
      {view.billing && <><dl className="billing-facts"><dt>Текущий контакт</dt><dd data-testid="current-contact">{view.billing.account.contact_display_name}</dd><dt>Версия контакта</dt><dd data-testid="contact-version">{view.billing.account.version}</dd><dt>Доступность</dt><dd>{view.billing.availability}</dd><dt>Режим сервиса</dt><dd>{view.billing.mode} · {view.billing.mode_active ? 'действует' : 'не действует'}</dd></dl>
        {view.billing.subscription ? <dl className="billing-facts"><dt>План / ревизия</dt><dd>{view.billing.subscription.plan.code} / {view.billing.subscription.plan.revision}</dd><dt>Подписка / финансирование</dt><dd>{view.billing.subscription.status} / {view.billing.subscription.funding_mode}</dd><dt>Период действия (UTC)</dt><dd>{view.billing.subscription.effective_from} — {view.billing.subscription.effective_until}</dd></dl> : <p className="empty">INACTIVE — текущей подписки нет.</p>}
        <p className="muted">Подписка и активность режима учитываются сервером независимо.</p>
        <ul className="decisions" aria-label="Серверные возможности">{view.billing.decisions.map(d => <li key={d.key}><span className="mono">{d.key}</span><strong>{d.type === 'LIMIT' ? `Лимит: ${d.limit}` : d.type === 'ENABLED' ? 'Разрешено' : reasons[d.reason]}</strong></li>)}</ul>
      </>}
      <form className="form contact-form" onSubmit={save}><h3>Контакт для подписки</h3><label htmlFor="billing-contact">Имя контакта</label><input id="billing-contact" value={matching && pending ? pending.body.contact_display_name : view.draft} onChange={e => editDraft(e.target.value)} disabled={!!pending || !view.billing || view.readBusy} autoComplete="off" aria-describedby="contact-help" /><p id="contact-help" className="muted">До 200 символов Unicode. Пробелы по краям удаляются сервером.</p><button disabled={!!pending || !view.billing || view.readBusy} type="submit">Сохранить контакт</button></form>
      {view.notice && <p role="status">{view.notice}</p>}
      {matching && pending && <div className="notice" aria-live="polite">
        {pending.phase === 'sending' && <p role="status">Сохраняем… Повторная отправка заблокирована.</p>}
        {pending.phase === 'confirmed' && <><p>Команда подтверждена; текущее состояние пока недоступно.</p><button disabled={view.readBusy} onClick={() => { if (!readInFlight.current) void read(); }}>Повторить чтение</button></>}
        {pending.phase === 'uncertain' && <><p>Результат сохранения неизвестен. Исходный запрос сохранён в памяти этой страницы.</p>{session === pending.failedSession ? <button onClick={recover}>Проверить сессию для повтора</button> : <button disabled={!view.billing || view.readBusy} onClick={() => void send(pending)}>Повторить исходное сохранение</button>}</>}
        {pending.phase === 'conflict' && <p role="alert">Нужно завершить конфликтующее намерение вручную.</p>}
        {pending.phase !== 'sending' && pending.phase !== 'confirmed' && <button className="secondary" onClick={discard}>Завершить намерение без повтора</button>}
      </div>}
      <section aria-label="Audit" className="audit"><div className="billing-heading"><h3>История изменений (Audit)</h3><button className="secondary" disabled={view.auditBusy} onClick={() => { if (!auditInFlight.current) void audit(); }}>Обновить историю</button></div>
        {view.auditBusy && <p role="status">Загружаем историю…</p>}{view.auditError && <p role="alert">{view.auditError}</p>}
        {view.rows?.length === 0 && <p>История пуста.</p>}
        <ol>{view.rows?.map(item => <li key={item.audit_event_id}><time dateTime={item.occurred_at}>{item.occurred_at}</time><strong>{item.event_type === 'WORKSPACE_BILLING_PROVISIONED' ? 'Подписка настроена' : item.event_type === 'MESSAGE_SEND_REQUESTED' ? 'Ручной ответ поставлен в очередь' : 'Контакт изменён'}</strong><span className="mono">{item.actor_kind === 'LOCAL_PROVISIONER' ? 'LOCAL_PROVISIONER' : `Пользователь ${item.actor_user_account_id}`}</span></li>)}</ol>
        {view.cursor !== null && <button disabled={view.auditBusy} onClick={() => { if (!auditInFlight.current) void audit(view.cursor); }}>Загрузить ещё</button>}
        {view.rows !== null && view.cursor === null && !view.auditBusy && <p className="muted">Конец истории.</p>}
      </section>
    </section>)}
  </>;
}
