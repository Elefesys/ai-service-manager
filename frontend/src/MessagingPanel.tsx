import { FormEvent, useEffect, useRef, useState } from 'react';
import { Session } from './api';
import { Connection, Conversation, Message, MessagingError, Page, ReadGrant, SendBody, SendReceipt, exactManualText, messagingApi } from './messaging-api';

type Intent = { readonly actor: string; readonly workspace: string; readonly conversation: string; readonly body: SendBody; readonly key: string; phase: 'sending' | 'uncertain' | 'confirmed' | 'conflict'; ambiguous: boolean; failedSession: Session; receipt?: SendReceipt };
type Collection<T> = { items: T[] | null; cursor: string | null; busy: boolean; error: string };
type ImageView = { message: string; busy: boolean; grant: ReadGrant | null; error: string };
type View = { generation: number; connections: Collection<Connection>; conversations: Collection<Conversation>; messages: Collection<Message>; selected: string; draft: string; notice: string; denied: boolean; image: ImageView | null; receipt: SendReceipt | null };
const empty = <T,>(): Collection<T> => ({ items: null, cursor: null, busy: false, error: '' });
const blank = (generation: number): View => ({ generation, connections: empty(), conversations: empty(), messages: empty(), selected: '', draft: '', notice: '', denied: false, image: null, receipt: null });
const connectionState: Record<Connection['state'], string> = { AVAILABLE: 'Доступно по наблюдению', DISABLED: 'Подключение отключено', RIGHTS_MISSING: 'Недостаточно прав', UNVERIFIED: 'Требует проверки', UNAVAILABLE: 'Последняя проверка не удалась' };
const deliveryState: Record<NonNullable<Message['delivery']>['status'], string> = { PENDING: 'В очереди', DISPATCHING: 'Отправка начата', SENT: 'Канал принял', FAILED: 'Отправка отклонена', UNKNOWN: 'Результат неизвестен — повтора нет' };
const failure = (e: unknown) => e instanceof MessagingError && e.code === 'BILLING_STATE_UNAVAILABLE' ? `Состояние подписки недоступно: ${e.stateReason}.` : e instanceof MessagingError && e.code === 'RATE_LIMITED' ? 'Слишком много запросов. Повторите позже.' : e instanceof MessagingError && e.code === 'INVALID_REQUEST' ? 'Страница недоступна. Обновите список с начала.' : 'Не удалось получить данные. Повторите чтение.';
function merge<T extends { created_at: string }>(old: T[], next: T[], id: (v: T) => string): T[] {
  // Later projections replace delivery/file state. Compare exact wire timestamps,
  // not Date milliseconds or provider occurred_at.
  return [...new Map([...old, ...next].map(v => [id(v), v])).values()].sort((a, b) => a.created_at === b.created_at ? (id(a) < id(b) ? 1 : id(a) > id(b) ? -1 : 0) : a.created_at < b.created_at ? 1 : -1);
}

// Page lifetime includes login/recovery. No storage, polling, or write on mount.
export function MessagingPanel({ session, workspace, recover, expired, accessDenied }: { session: Session | null; workspace: string; recover: () => void; expired: () => void; accessDenied?: () => void }) {
  const owner = !!session && !!workspace && session.memberships.some(m => m.workspace_id === workspace && m.role === 'OWNER');
  const scope = useRef({ session, workspace, owner, generation: 0 });
  const selection = useRef({ id: '', epoch: 0 });
  if (scope.current.session !== session || scope.current.workspace !== workspace || scope.current.owner !== owner) {
    scope.current = { session, workspace, owner, generation: scope.current.generation + 1 };
    selection.current = { id: '', epoch: selection.current.epoch + 1 };
  }
  const generation = scope.current.generation;
  const [stored, setView] = useState<View>(() => blank(generation));
  const view = stored.generation === generation ? stored : blank(generation);
  const imageState = useRef(view.image);
  imageState.current = view.image;
  const intent = useRef<Intent | null>(null);
  const [, redraw] = useState(0);
  const alive = useRef(true), denied = useRef(-1);
  const controllers = useRef(new Set<AbortController>());
  const sequence = useRef({ connections: 0, conversations: 0, messages: 0, image: 0 });
  const reading = useRef({ connections: false, conversations: false, messages: false });
  const current = () => alive.current && scope.current.generation === generation && scope.current.owner && denied.current !== generation;
  const inConversation = (id: string, epoch: number) => current() && selection.current.id === id && selection.current.epoch === epoch;
  const update = (patch: Partial<View>) => { if (current()) setView(v => ({ ...(v.generation === generation ? v : blank(generation)), ...patch })); };
  const changed = () => redraw(n => n + 1);
  const controller = () => { const c = new AbortController(); controllers.current.add(c); return c; };
  const sameActor = (p: Intent) => p.actor === session?.user_account_id && p.workspace === workspace;
  const matching = !!intent.current && sameActor(intent.current) && intent.current.conversation === view.selected;
  function interruptSend() {
    if (intent.current?.phase === 'sending') { intent.current.phase = 'uncertain'; intent.current.ambiguous = true; changed(); }
  }
  function authorization(e: unknown): boolean {
    if (!(e instanceof MessagingError)) return false;
    if (e.status === 401 && e.code === 'SESSION_REQUIRED') { interruptSend(); expired(); return true; }
    if (e.status === 403 && e.code === 'CSRF_REJECTED') { interruptSend(); recover(); return true; }
    if (e.status === 403) {
      interruptSend(); denied.current = generation;
      controllers.current.forEach(c => c.abort());
      setView({ ...blank(generation), denied: true });
      accessDenied?.();
      return true;
    }
    return false;
  }
  async function list(kind: 'connections' | 'conversations', cursor: string | null = null) {
    if (!current() || reading.current[kind]) return;
    reading.current[kind] = true;
    const seq = ++sequence.current[kind], c = controller();
    setView(v => ({ ...v, [kind]: { ...(cursor === null ? empty() : v[kind]), busy: true, error: '' } }));
    try {
      const page = await messagingApi[kind](workspace, cursor, c.signal);
      if (!current() || seq !== sequence.current[kind]) return;
      setView(v => {
        if (kind === 'connections') {
          const p = page as Page<Connection>;
          return { ...v, connections: { items: merge(cursor === null ? [] : v.connections.items ?? [], p.items, x => x.connection_id), cursor: p.next_cursor, busy: false, error: '' } };
        }
        const p = page as Page<Conversation>;
        return { ...v, conversations: { items: merge(cursor === null ? [] : v.conversations.items ?? [], p.items, x => x.conversation_id), cursor: p.next_cursor, busy: false, error: '' } };
      });
      if (kind === 'conversations' && !selection.current.id && page.items.length) {
        const p = intent.current;
        const original = p && sameActor(p) ? (page.items as Conversation[]).find(v => v.conversation_id === p.conversation) : undefined;
        choose((original ?? (page.items as Conversation[])[0]).conversation_id);
      }
    } catch (e) {
      if (!current() || seq !== sequence.current[kind]) return;
      if (!authorization(e)) setView(v => ({ ...v, [kind]: { ...v[kind], busy: false, error: failure(e) } }));
    } finally { controllers.current.delete(c); if (current() && seq === sequence.current[kind]) reading.current[kind] = false; }
  }
  async function history(id = selection.current.id, cursor: string | null = null) {
    if (!current() || !id || reading.current.messages || intent.current?.phase === 'sending') return;
    // Only a read begun after acceptance may finish receipt recovery.
    const confirmed = intent.current?.phase === 'confirmed' ? intent.current : null;
    const epoch = selection.current.epoch, seq = ++sequence.current.messages, c = controller();
    reading.current.messages = true;
    if (cursor === null) { sequence.current.image++; update({ image: null }); }
    setView(v => ({ ...v, messages: { ...(cursor === null ? empty<Message>() : v.messages), busy: true, error: '' } }));
    try {
      const page = await messagingApi.messages(workspace, id, cursor, c.signal);
      if (!inConversation(id, epoch) || seq !== sequence.current.messages) return;
      setView(v => ({ ...v, messages: { items: merge(cursor === null ? [] : v.messages.items ?? [], page.items, x => x.message_id), cursor: page.next_cursor, busy: false, error: '' } }));
      const p = intent.current;
      if (p && p === confirmed && p.phase === 'confirmed' && sameActor(p) && p.conversation === id) {
        update({ receipt: p.receipt!, notice: 'Намерение принято. Доставка показана по текущей истории.', draft: '' });
        intent.current = null; changed();
      }
    } catch (e) {
      if (!inConversation(id, epoch) || seq !== sequence.current.messages) return;
      if (!authorization(e)) setView(v => ({ ...v, messages: { ...v.messages, busy: false, error: failure(e) } }));
    } finally { controllers.current.delete(c); if (inConversation(id, epoch) && seq === sequence.current.messages) reading.current.messages = false; }
  }
  function choose(id: string) {
    if (!current() || selection.current.id === id) return;
    interruptSend();
    selection.current = { id, epoch: selection.current.epoch + 1 };
    sequence.current.messages++; sequence.current.image++; reading.current.messages = false;
    update({ selected: id, messages: empty(), image: null, draft: '', notice: '', receipt: null });
    void history(id);
  }
  useEffect(() => {
    alive.current = true; interruptSend();
    setView(blank(generation));
    reading.current = { connections: false, conversations: false, messages: false };
    if (owner) { void list('connections'); void list('conversations'); }
    return () => { alive.current = false; controllers.current.forEach(c => c.abort()); controllers.current.clear(); };
  }, [generation]);

  async function send(p: Intent) {
    const id = selection.current.id, epoch = selection.current.epoch;
    if (!session || !current() || reading.current.messages || !sameActor(p) || p.conversation !== id || intent.current !== p || p.phase === 'sending' || p.phase === 'confirmed' || p.phase === 'conflict') return;
    p.phase = 'sending'; p.failedSession = session; changed(); update({ notice: '' });
    const c = controller();
    try {
      const receipt = await messagingApi.send(workspace, id, p.body, p.key, session.csrf_token, c.signal);
      if (!inConversation(id, epoch) || intent.current !== p) return;
      p.phase = 'confirmed'; p.receipt = Object.freeze(receipt); changed();
      update({ receipt, draft: '', notice: 'Намерение принято сервером. Это ещё не доставка.' });
      // The receipt is final even if this read fails. Never put the GET in the
      // POST recovery catch: only reads may follow a valid 202.
      void history(id);
    } catch (e) {
      if (!inConversation(id, epoch) || intent.current !== p) return;
      p.phase = 'uncertain'; changed();
      if (e instanceof MessagingError && e.code === 'IDEMPOTENCY_KEY_CONFLICT') {
        p.phase = 'conflict'; update({ notice: 'Конфликт ключа. Повтор исходного ответа остановлен.' }); return;
      }
      if (e instanceof MessagingError && [401,403].includes(e.status)) {
        p.ambiguous = true;
        if (authorization(e)) return;
      }
      const definitive = e instanceof MessagingError && [404,409,413,415,422,429].includes(e.status);
      if (definitive && !p.ambiguous) {
        intent.current = null; changed();
        update({ draft: p.body.text, notice: e.code === 'NOT_ALLOWED' ? 'Сервер не разрешил новый ответ. Черновик сохранён.' : 'Запрос отклонён. Проверьте черновик перед новой отправкой.' });
      } else {
        p.ambiguous = true;
        update({ notice: e instanceof MessagingError && e.code === 'BILLING_STATE_UNAVAILABLE' ? failure(e) : definitive ? 'Эта попытка отклонена; результат прежней попытки всё ещё неизвестен.' : '' });
      }
    } finally { controllers.current.delete(c); }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!session || !current() || intent.current || !view.selected || reading.current.messages) return;
    try { exactManualText(view.draft); } catch { update({ notice: 'Введите 1–4096 символов Unicode: не только пробелы, без NUL и одиночных суррогатов.' }); return; }
    const p: Intent = { actor: session.user_account_id, workspace, conversation: view.selected, body: Object.freeze({ text: view.draft }), key: crypto.randomUUID(), phase: 'uncertain', ambiguous: false, failedSession: session };
    intent.current = p; void send(p);
  }
  function discard() {
    if (intent.current?.phase === 'sending' && matching) return;
    intent.current = null; changed();
    update({ draft: '', notice: 'Намерение завершено без повтора. Это не отменяет возможную серверную команду.' });
  }
  async function openImage(message: Message) {
    if (!session || !current() || message.file?.status !== 'READY') return;
    const id = selection.current.id, epoch = selection.current.epoch, seq = ++sequence.current.image, c = controller();
    update({ image: { message: message.message_id, busy: true, grant: null, error: '' } });
    try {
      const grant = await messagingApi.grant(workspace, id, message.message_id, message.file.file_id, session.csrf_token, c.signal);
      if (!inConversation(id, epoch) || seq !== sequence.current.image) return;
      update({ image: { message: message.message_id, busy: false, grant: Date.parse(grant.expires_at) > Date.now() ? grant : null, error: Date.parse(grant.expires_at) > Date.now() ? '' : 'Ссылка истекла. Запросите доступ снова.' } });
    } catch (e) {
      if (!inConversation(id, epoch) || seq !== sequence.current.image) return;
      if (!authorization(e)) update({ image: { message: message.message_id, busy: false, grant: null, error: 'Изображение недоступно. Можно запросить доступ снова.' } });
    } finally { controllers.current.delete(c); }
  }
  const grant = view.image?.grant;
  useEffect(() => {
    if (!grant) return;
    const id = selection.current.id, epoch = selection.current.epoch, seq = sequence.current.image;
    const timer = setTimeout(() => {
      if (inConversation(id, epoch) && seq === sequence.current.image) setView(v => ({ ...v, image: v.image ? { ...v.image, grant: null, error: 'Ссылка истекла. Запросите доступ снова.' } : null }));
    }, Math.min(60000, Math.max(0, Date.parse(grant.expires_at) - Date.now())));
    return () => clearTimeout(timer);
  }, [grant, generation]);

  const p = intent.current, detached = p && (!matching || !owner || view.denied);
  const selected = view.conversations.items?.find(c => c.conversation_id === view.selected);
  return <>
    {detached && <section className="panel alert" aria-label="Незавершённый ответ"><p role="status">В прежнем контексте осталось намерение ответа. Оно не переносится и не отправляется в этом контексте.</p><button onClick={discard}>Завершить ответ без повтора</button></section>}
    {owner && (view.denied ? <section className="panel alert" role="alert"><h2>Нет доступа к переписке</h2><p>История и изображения скрыты.</p><button onClick={recover}>Проверить доступ к переписке</button></section> : <section className="panel messaging" aria-label="Переписка">
      <div className="billing-heading"><div><span className="kicker">OWNER</span><h2>Переписка</h2></div></div>
      <section aria-label="Подключения"><div className="billing-heading"><h3>Подключения</h3><button className="secondary" disabled={view.connections.busy} onClick={() => void list('connections')}>Обновить подключения</button></div>
        <p className="muted">Это наблюдение. Права, окно ответа и разрешение на отправку проверяются сервером заново.</p>
        {view.connections.busy && <p role="status">Загружаем подключения…</p>}{view.connections.error && <p role="alert">{view.connections.error}</p>}
        {view.connections.items?.length === 0 && <p>Подключений нет.</p>}
        <ul className="connection-list">{view.connections.items?.map(c => <li key={c.connection_id} data-testid={`connection-${c.connection_id}`}><strong>{c.provider === 'CONTROLLED' ? 'CONTROLLED · LOCAL/TEST' : 'Telegram'} · {connectionState[c.state]}</strong><span className="mono">{c.connection_id}</span><small>Наблюдение: {c.observed_at ?? 'Нет отметки Telegram'}</small></li>)}</ul>
        {view.connections.cursor && <button disabled={view.connections.busy} onClick={() => void list('connections', view.connections.cursor)}>Ещё подключения</button>}
      </section>
      <div className="messaging-columns"><section aria-label="Диалоги"><div className="billing-heading"><h3>Диалоги</h3><button className="secondary" disabled={view.conversations.busy} onClick={() => void list('conversations')}>Обновить диалоги</button></div>
        {view.conversations.busy && <p role="status">Загружаем диалоги…</p>}{view.conversations.error && <p role="alert">{view.conversations.error}</p>}
        {view.conversations.items?.length === 0 && <p>Диалогов пока нет.</p>}
        <ul className="conversation-list">{view.conversations.items?.map(c => <li key={c.conversation_id}><button className="secondary" aria-pressed={view.selected === c.conversation_id} data-testid={`conversation-${c.conversation_id}`} onClick={() => choose(c.conversation_id)}>Клиент {c.client_id.slice(0,8)}<small className="mono">Диалог {c.conversation_id.slice(0,8)}</small></button></li>)}</ul>
        {view.conversations.cursor && <button disabled={view.conversations.busy} onClick={() => void list('conversations', view.conversations.cursor)}>Ещё диалоги</button>}
      </section>
      <section aria-label="История сообщений"><div className="billing-heading"><h3>История сообщений</h3><button className="secondary" disabled={!view.selected || view.messages.busy || p?.phase === 'sending'} onClick={() => void history()}>Обновить сообщения</button></div>
        {!view.selected && <p>Выберите диалог.</p>}
        {selected && <p className="muted">Окно ответа: {selected.reply_window_expires_at ?? 'Нет отметки Telegram'}. Текущее разрешение проверяет сервер.</p>}
        {view.messages.busy && <p role="status">Загружаем сообщения…</p>}{view.messages.error && <p role="alert">{view.messages.error}</p>}
        {view.messages.items?.length === 0 && <p>Сообщений пока нет.</p>}
        <ol className="message-list">{view.messages.items?.map(m => <li key={m.message_id} data-testid={`message-${m.message_id}`}><article>
          <strong>{m.direction === 'INBOUND' ? 'Входящее' : 'Ручной ответ'}</strong><time dateTime={m.occurred_at}>{m.occurred_at}</time>
          {m.text !== null && <p className="message-text">{m.text}</p>}
          {m.delivery && <p className="delivery" role="status">{deliveryState[m.delivery.status]}{m.delivery.error_code && ` · ${m.delivery.error_code}`}</p>}
          {m.file && <div className="message-image">
            {m.file.status === 'PENDING' && <p>Изображение загружается.</p>}
            {m.file.status === 'FAILED' && <p>Изображение недоступно · {m.file.error_code}</p>}
            {m.file.status === 'READY' && <><p>{m.file.manifest!.mime_type} · {m.file.manifest!.width} × {m.file.manifest!.height} · {m.file.manifest!.size_bytes} байт</p><button className="secondary" disabled={view.image?.message === m.message_id && view.image.busy} onClick={() => void openImage(m)}>Открыть изображение</button></>}
            {view.image?.message === m.message_id && <>{view.image.busy && <p role="status">Проверяем доступ к изображению…</p>}{view.image.error && <p role="alert">{view.image.error}</p>}{view.image.grant && <img key={view.image.grant.url} alt="Изображение из диалога" src={view.image.grant.url} crossOrigin="anonymous" referrerPolicy="no-referrer" onError={() => { if (current() && imageState.current === view.image) update({ image: { message: m.message_id, busy: false, grant: null, error: 'Изображение не загрузилось. Запросите доступ снова.' } }); }} />}</>}
          </div>}
        </article></li>)}</ol>
        {view.messages.cursor && <button disabled={view.messages.busy || p?.phase === 'sending'} onClick={() => void history(view.selected, view.messages.cursor)}>Ещё сообщения</button>}
        {view.messages.items !== null && view.messages.cursor === null && !view.messages.busy && <p className="muted">Начало истории.</p>}
        <p className="muted">«Канал принял» не означает получение или прочтение клиентом. UNKNOWN не отправляется повторно.</p>
        {view.selected && <form className="form reply-form" onSubmit={submit}><label htmlFor="manual-reply">Ручной текстовый ответ</label><textarea id="manual-reply" rows={4} value={matching && p && p.phase !== 'confirmed' ? p.body.text : view.draft} onChange={e => update({ draft: e.target.value })} disabled={!!p} aria-describedby="reply-help" /><p id="reply-help" className="muted">1–4096 символов Unicode. Пробелы и переносы сохраняются; Enter добавляет строку.</p><button type="submit" disabled={!!p || view.messages.busy}>Проверить и отправить</button></form>}
        {view.notice && <p role="status">{view.notice}</p>}
        {view.receipt && <p className="muted">Принятие намерения: {view.receipt.accepted_at}. Текущее состояние — в истории, даже если сообщение находится на другой странице.</p>}
        {matching && p && <div className="notice" aria-live="polite">
          {p.phase === 'sending' && <p>Принимаем намерение… Повторная отправка заблокирована.</p>}
          {p.phase === 'confirmed' && <><p>Намерение подтверждено. Повторяется только чтение.</p><button disabled={view.messages.busy} onClick={() => void history()}>Повторить чтение сообщений</button></>}
          {p.phase === 'uncertain' && <><p>Результат запроса неизвестен. Исходный ответ сохранён в памяти страницы.</p>{session === p.failedSession ? <button onClick={recover}>Проверить сессию для ответа</button> : <button disabled={view.messages.busy} onClick={() => void send(p)}>Повторить исходный ответ</button>}</>}
          {p.phase === 'conflict' && <p role="alert">Конфликтующее намерение требует ручного завершения.</p>}
          {p.phase !== 'sending' && p.phase !== 'confirmed' && <button className="secondary" onClick={discard}>Завершить ответ без повтора</button>}
        </div>}
      </section></div>
    </section>)}
  </>;
}
