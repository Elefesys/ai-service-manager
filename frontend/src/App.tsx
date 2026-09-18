import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, Business, Session } from './api';

type Phase = 'checking' | 'anonymous' | 'authenticated' | 'recovering' | 'uncertain';
const message = (error: unknown) => error instanceof ApiError && error.code === 'RATE_LIMITED' ? `Слишком много запросов. Повторите позже${error.retryAfter ? ` (${error.retryAfter})` : ''}.` : 'Сервис временно недоступен. Повторите проверку.';

export function App({ pathname = window.location.pathname }: { pathname?: string }) {
  if (pathname.startsWith('/ops')) return <Ops />;
  return <Console />;
}

function Console() {
  const [phase, setPhase] = useState<Phase>('checking');
  const [session, setSession] = useState<Session | null>(null);
  const [workspace, setWorkspace] = useState('');
  const [businesses, setBusinesses] = useState<Business[] | null>(null);
  const [selected, setSelected] = useState<Business | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const controllers = useRef(new Set<AbortController>());
  const mounted = useRef(true);
  const logoutIntent = useRef(false);
  const own = () => { const c = new AbortController(); controllers.current.add(c); return c; };
  const resetProtected = useCallback(() => { generation.current++; controllers.current.forEach((c) => c.abort()); controllers.current.clear(); setSession(null); setWorkspace(''); setBusinesses(null); setSelected(null); }, []);
  const accept = useCallback((next: Session) => { resetProtected(); setSession(next); setWorkspace(next.memberships[0]?.workspace_id ?? ''); setPhase('authenticated'); setError(''); }, [resetProtected]);

  const checkSession = useCallback(async (recovery = false) => {
    const c = own(); setPhase(recovery ? 'recovering' : 'checking'); setError('');
    try { accept(await api.session(c.signal)); }
    catch (e) {
      if (c.signal.aborted || !mounted.current) return;
      resetProtected();
      if (e instanceof ApiError && e.status === 401 && e.code === 'SESSION_REQUIRED') setPhase('anonymous');
      else { setPhase('uncertain'); setError(message(e)); }
    } finally { controllers.current.delete(c); }
  }, [accept, resetProtected]);

  useEffect(() => { mounted.current = true; void checkSession(); return () => { mounted.current = false; controllers.current.forEach((c) => c.abort()); }; }, [checkSession]);
  useEffect(() => {
    const verify = () => { if (document.visibilityState === 'visible' && session && !busy) void checkSession(true); };
    window.addEventListener('focus', verify); document.addEventListener('visibilitychange', verify);
    return () => { window.removeEventListener('focus', verify); document.removeEventListener('visibilitychange', verify); };
  }, [session, busy, checkSession]);
  useEffect(() => {
    if (!session || !workspace) { setBusinesses(session ? [] : null); return; }
    const owner = ++generation.current; const principal = session.user_account_id; const c = own(); setBusinesses(null); setSelected(null); setError('');
    void api.businesses(workspace, c.signal).then((items) => { if (owner === generation.current && session.user_account_id === principal) setBusinesses(items); }).catch((e) => {
      if (c.signal.aborted || owner !== generation.current) return;
      setBusinesses([]); setSelected(null);
      if (e instanceof ApiError && e.status === 401) { resetProtected(); setPhase('anonymous'); setError('Сессия завершена. Войдите снова.'); }
      else if (e instanceof ApiError && e.status === 403) setError('Нет доступа к выбранному Workspace.');
      else if (e instanceof ApiError && e.status === 404) setError('Workspace не найден или недоступен.');
      else setError(message(e));
    }).finally(() => controllers.current.delete(c));
    return () => c.abort();
  }, [workspace, session?.user_account_id, resetProtected]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return; setBusy(true); setError('');
    const form = event.currentTarget; const data = new FormData(form); const loginValue = String(data.get('login') ?? ''); const password = String(data.get('password') ?? '');
    const passwordInput = form.elements.namedItem('password') as HTMLInputElement; passwordInput.value = '';
    if (loginValue.length < 3 || loginValue.length > 72 || password.length < 15 || password.length > 128) { setError('Проверьте длину логина и пароля.'); setBusy(false); return; }
    const c = own();
    try { const challenge = await api.bootstrap(c.signal); accept(await api.login(loginValue, password, challenge.csrf_token, c.signal)); }
    catch (e) {
      if (c.signal.aborted) return;
      if (e instanceof ApiError && e.code === 'INVALID_CREDENTIALS') { resetProtected(); setPhase('anonymous'); setError('Неверный логин или пароль.'); }
      else await recoverMutation(e);
    } finally { setBusy(false); controllers.current.delete(c); }
  }
  async function recoverMutation(cause: unknown, intent = false) {
    resetProtected(); setPhase('recovering'); setError('Результат операции уточняется у сервера…');
    const c = own();
    try {
      const actual = await api.session(c.signal);
      if (intent) { logoutIntent.current = true; await finishLogout(actual, false); } else accept(actual);
    } catch (e) {
      if (c.signal.aborted) return;
      if (e instanceof ApiError && e.status === 401) { logoutIntent.current = false; setPhase('anonymous'); setError(intent ? 'Выход подтверждён текущей проверкой сессии.' : 'Сессия не создана. Попробуйте войти снова.'); }
      else { setPhase('uncertain'); setError(message(cause)); }
    } finally { controllers.current.delete(c); }
  }
  async function finishLogout(actual = session, allowRecovery = true) {
    if (!actual) return; resetProtected(); setBusy(true); const c = own();
    try { await api.logout(actual.csrf_token, c.signal); logoutIntent.current = false; setPhase('anonymous'); setError('Выход выполнен и подтверждён сервером.'); }
    catch (e) { if (!c.signal.aborted) { if (allowRecovery) await recoverMutation(e, true); else { setPhase('uncertain'); setError(message(e)); } } }
    finally { setBusy(false); controllers.current.delete(c); }
  }
  async function rotate() {
    if (!session || busy) return; setBusy(true); const oldExpiry = session.expires_at; const c = own();
    try { const next = await api.rotate(session.csrf_token, c.signal); if (next.expires_at !== oldExpiry) throw new ApiError(502, 'INVALID_RESPONSE'); accept(next); setError('Защита сессии обновлена; срок действия не продлён.'); }
    catch (e) { if (!c.signal.aborted) await recoverMutation(e); } finally { setBusy(false); controllers.current.delete(c); }
  }
  async function selectBusiness(id: string) {
    if (!session || !workspace) return; const owner = generation.current; const c = own(); setSelected(null);
    try { const item = await api.business(workspace, id, c.signal); if (owner === generation.current) setSelected(item); }
    catch (e) { if (!c.signal.aborted && owner === generation.current) setError(e instanceof ApiError && e.status === 404 ? 'Business не найден или недоступен.' : message(e)); }
    finally { controllers.current.delete(c); }
  }

  return <Shell title="Business Console">
    <p className="lede">Безопасный LOCAL/TEST доступ к доступным Workspace и Business.</p>
    {(phase === 'checking' || phase === 'recovering') && <section className="panel center" aria-busy="true"><div className="spinner" /><h2>{phase === 'checking' ? 'Проверяем сессию' : 'Уточняем результат'}</h2><p>Защищённые данные пока скрыты.</p></section>}
    {phase === 'uncertain' && <section className="panel alert" role="alert"><h2>Состояние сессии неизвестно</h2><p>{error}</p><button onClick={() => void checkSession(true)}>Проверить снова</button></section>}
    {phase === 'anonymous' && <section className="auth-grid"><div><span className="kicker">SERVER SESSION</span><h2>Вход в консоль</h2><p>Используйте синтетическую учётную запись LOCAL/TEST. Регистрация и восстановление пароля здесь не реализованы.</p></div><form className="panel form" onSubmit={(e) => void login(e)}><label htmlFor="login">Логин</label><input id="login" name="login" autoComplete="username" minLength={3} maxLength={72} required /><label htmlFor="password">Пароль</label><input id="password" name="password" type="password" autoComplete="current-password" minLength={15} maxLength={128} required /><button disabled={busy} type="submit">{busy ? 'Входим…' : 'Войти'}</button>{error && <p className="error" role="alert">{error}</p>}</form></section>}
    {phase === 'authenticated' && session && <><section className="identity"><div><span className="kicker">ACTIVE SESSION</span><h2>Рабочее пространство</h2><p className="mono">Пользователь {session.user_account_id}</p></div><div className="actions"><button className="secondary" disabled={busy} onClick={() => void rotate()}>Обновить защиту сессии</button><button className="danger" disabled={busy} onClick={() => { logoutIntent.current = true; void finishLogout(); }}>Выйти</button></div></section><section className="panel"><label htmlFor="workspace">Workspace</label><select id="workspace" value={workspace} onChange={(e) => { generation.current++; setBusinesses(null); setSelected(null); setWorkspace(e.target.value); }}>{session.memberships.map((m) => <option value={m.workspace_id} key={m.workspace_id}>{m.workspace_id} · {m.role}</option>)}</select>{session.memberships.length === 0 && <p className="empty">Нет доступных memberships.</p>}<p className="muted">Сессия действует до: {session.expires_at} (решение об истечении принимает сервер).</p></section>{error && <p className="banner" role="alert">{error}</p>}<section className="panel"><h2>Business</h2>{businesses === null && workspace && <p role="status">Загружаем список…</p>}{businesses?.length === 0 && <p className="empty">В этом Workspace нет доступных Business.</p>}<div className="cards">{businesses?.map((b) => <button className="business" key={b.id} onClick={() => void selectBusiness(b.id)}><strong>{b.name}</strong><span>{b.status} · v{b.version}</span><span className="mono">{b.id}</span></button>)}</div>{selected && <article className="detail"><span className="kicker">DETAIL</span><h3>{selected.name}</h3><dl><dt>Status</dt><dd>{selected.status}</dd><dt>Version</dt><dd>{selected.version}</dd><dt>Business ID</dt><dd className="mono">{selected.id}</dd></dl></article>}</section></>}
  </Shell>;
}

function Ops() {
  const [state, setState] = useState<'checking' | 'ok' | 'bad'>('checking');
  useEffect(() => { const c = new AbortController(); const timer = setTimeout(() => c.abort(), 5000); void fetch('/health/ready', { signal: c.signal }).then(async (r) => { const v: unknown = await r.json(); setState(r.ok && typeof v === 'object' && v !== null && 'status' in v && v.status === 'ok' && 'component' in v && v.component === 'database' ? 'ok' : 'bad'); }).catch(() => setState('bad')).finally(() => clearTimeout(timer)); return () => { clearTimeout(timer); c.abort(); }; }, []);
  return <Shell title="Platform Operations"><section className="panel notice"><h2>Техническая shell</h2><p>Business-сессия не предоставляет операторских прав. Tenant-данные и privileged actions здесь отсутствуют.</p></section><section className="panel"><h2>Readiness backend</h2><p role="status">{state === 'checking' ? 'Проверка…' : state === 'ok' ? 'Проверка готовности пройдена' : 'Сервис недоступен или не готов'}</p></section></Shell>;
}
function Shell({ title, children }: { title: string; children: React.ReactNode }) { return <main><header><div><span className="eyebrow">AI SERVICE MANAGER</span><span className="badge">LOCAL / TEST</span></div><h1>{title}</h1></header><nav aria-label="Разделы"><a href="/">Business Console</a><a href="/ops/">Platform Operations</a></nav>{children}<footer>Ограниченный M1.2 preview — не production CRM.</footer></main>; }
