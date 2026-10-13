import { MutableRefObject, ReactNode, useEffect, useRef, useState } from 'react';
import { Session } from './api';
import { ControlBody, ControlContext, ControlError, ControlOperation, ControlReceipt, ControlState, controlApi } from './conversation-control-api';

export type ControlIntent = {
  readonly actor: string; readonly workspace: string; readonly conversation: string; readonly client: string;
  readonly operation: ControlOperation; readonly body: ControlBody; readonly key: string;
  phase: 'sending' | 'uncertain' | 'confirmed' | 'conflict'; ambiguous: boolean; failedSession: Session; receipt?: ControlReceipt;
};
type View = { generation: number; state: ControlState | null; busy: boolean; error: string; notice: string; denied: boolean };
const blank = (generation: number): View => ({generation,state:null,busy:false,error:'',notice:'',denied:false});
const failure = (e: unknown) => e instanceof ControlError && e.code === 'BILLING_STATE_UNAVAILABLE' ? 'Состояние подписки недоступно серверу.' : e instanceof ControlError && e.code === 'RATE_LIMITED' ? 'Слишком много запросов. Повторите позже.' : 'Текущий режим недоступен. Повторите чтение.';

// Stays mounted with MessagingPanel during login and selection changes. The
// render slot places its view next to the selected conversation without losing
// the memory-only intent. The shared ref also blocks synchronous manual submit.
export function ConversationControl({session,context,intent,manualPending,refresh,accepted,recover,expired,accessDenied,children}: {
  session: Session | null; context: ControlContext | null; intent: MutableRefObject<ControlIntent | null>;
  manualPending: () => boolean; refresh: number; accepted: () => void;
  recover: () => void; expired: () => void; accessDenied: () => void;
  children?: (control: ReactNode, pending: boolean) => ReactNode;
}) {
  const owner = !!session && !!context && session.memberships.some(m=>m.workspace_id===context.workspace&&m.role==='OWNER');
  const scope = useRef({session,workspace:context?.workspace,conversation:context?.conversation,client:context?.client,owner,generation:0});
  if (scope.current.session!==session || scope.current.workspace!==context?.workspace || scope.current.conversation!==context?.conversation || scope.current.client!==context?.client || scope.current.owner!==owner)
    scope.current={session,workspace:context?.workspace,conversation:context?.conversation,client:context?.client,owner,generation:scope.current.generation+1};
  const generation=scope.current.generation;
  const [stored,setView]=useState<View>(()=>blank(generation));
  const view=stored.generation===generation?stored:blank(generation);
  const [,redraw]=useState(0);
  const alive=useRef(true), denied=useRef(-1), reading=useRef(false), sequence=useRef(0);
  const controllers=useRef(new Set<AbortController>());
  const current=()=>alive.current&&scope.current.generation===generation&&scope.current.owner&&denied.current!==generation;
  const matches=(p:ControlIntent)=>p.actor===session?.user_account_id&&p.workspace===context?.workspace&&p.conversation===context?.conversation&&p.client===context?.client;
  const update=(v:Partial<View>)=>{if(current())setView(old=>({...old,...v}));};
  const changed=()=>redraw(n=>n+1);
  const controller=()=>{const c=new AbortController();controllers.current.add(c);return c;};
  function interrupt() {if(intent.current?.phase==='sending'){intent.current.phase='uncertain';intent.current.ambiguous=true;}}
  function authorization(e:unknown) {
    if(!(e instanceof ControlError))return false;
    if(e.status===401&&e.code==='SESSION_REQUIRED'){interrupt();expired();return true;}
    if(e.status===403&&e.code==='CSRF_REJECTED'){interrupt();recover();return true;}
    if(e.status===403){interrupt();denied.current=generation;controllers.current.forEach(c=>c.abort());setView({...blank(generation),denied:true});accessDenied();return true;}
    return false;
  }
  async function read() {
    if(!context||!current()||reading.current||intent.current?.phase==='sending')return;
    const confirmed=intent.current?.phase==='confirmed'&&matches(intent.current)?intent.current:null;
    const seq=++sequence.current,c=controller();reading.current=true;update({state:null,busy:true,error:''});
    try {
      const state=await controlApi.read(context,c.signal);
      if(!current()||seq!==sequence.current)return;
      update({state,busy:false});
      if(confirmed&&intent.current===confirmed){intent.current=null;update({notice:'Операция подтверждена. Текущее состояние получено.'});changed();}
    } catch(e) {
      if(!current()||seq!==sequence.current)return;
      update({state:null,busy:false,error:failure(e)});authorization(e);
    } finally {controllers.current.delete(c);if(current()&&seq===sequence.current)reading.current=false;}
  }
  useEffect(()=>{
    alive.current=true;interrupt();reading.current=false;sequence.current++;setView(blank(generation));
    if(owner)void read();
    return ()=>{alive.current=false;interrupt();controllers.current.forEach(c=>c.abort());controllers.current.clear();};
  },[generation]);
  const refreshed=useRef(refresh);
  useEffect(()=>{if(refreshed.current!==refresh){refreshed.current=refresh;sequence.current++;reading.current=false;void read();}},[refresh]);

  async function send(p:ControlIntent) {
    if(!session||!context||!current()||!matches(p)||intent.current!==p||manualPending()||reading.current||p.phase==='sending'||p.phase==='confirmed'||p.phase==='conflict')return;
    p.phase='sending';p.failedSession=session;changed();update({state:null,notice:'',error:''});
    const c=controller();
    try {
      const receipt=await controlApi.command(context,p.operation,p.body,p.key,session.csrf_token,c.signal);
      if(!current()||intent.current!==p)return;
      p.phase='confirmed';p.receipt=receipt;changed();update({notice:'Операция подтверждена сервером. Проверяем текущий режим.'});
      // A failed read never returns the confirmed POST to the retry path.
      accepted();void read();
    } catch(e) {
      if(!current()||intent.current!==p)return;
      p.phase='uncertain';changed();
      if(e instanceof ControlError&&e.code==='IDEMPOTENCY_KEY_CONFLICT'){p.phase='conflict';update({notice:'Конфликт ключа. Повтор операции остановлен.'});return;}
      if(e instanceof ControlError&&[401,403].includes(e.status)){p.ambiguous=true;if(authorization(e))return;}
      const definitive=e instanceof ControlError&&[404,409,413,415,422,429].includes(e.status);
      if(definitive&&!p.ambiguous){
        intent.current=null;changed();
        update({notice:e.code==='STALE_STATE'?'Состояние изменилось. Проверьте свежий режим и выберите действие заново.':e.code==='NOT_ALLOWED'?'Сервер не разрешил автоматику. Управление можно забрать независимо от доступности отправки.':e.code==='CONTROL_VERSION_EXHAUSTED'?'Сервер не может изменить режим: счётчик версий исчерпан.':'Операция отклонена. Проверьте состояние перед новым действием.'});
        void read();
      } else {p.ambiguous=true;update({notice:definitive?'Эта попытка отклонена; результат прежней попытки всё ещё неизвестен.':''});}
    } finally {controllers.current.delete(c);}
  }
  function start(operation:ControlOperation) {
    if(!session||!context||!current()||!view.state||reading.current||intent.current||manualPending())return;
    const p:ControlIntent={actor:session.user_account_id,...context,operation,body:Object.freeze({expected_client_id:view.state.client_id,expected_control_generation:view.state.control_generation,expected_context_version:view.state.context_version}),key:crypto.randomUUID(),phase:'uncertain',ambiguous:false,failedSession:session};
    intent.current=p;void send(p);
  }
  function discard() {
    if(intent.current?.phase==='sending'&&matches(intent.current))return;
    intent.current=null;changed();update({notice:'Ожидание завершено без повтора. Это не отменяет возможную серверную операцию.'});void read();
  }
  const p=intent.current, matching=!!p&&matches(p)&&owner&&!view.denied;
  const control=owner&&context&&!view.denied?<section className="conversation-control" aria-label="Управление диалогом">
    <div className="billing-heading"><h3>Управление диалогом</h3><button className="secondary" disabled={view.busy||p?.phase==='sending'} onClick={()=>void read()}>Обновить режим</button></div>
    {view.busy&&<p role="status">Проверяем текущий режим…</p>}{view.error&&<p role="alert">{view.error}</p>}
    {view.state&&<><p role="status" className="control-mode">{view.state.control_mode==='HUMAN'?'Управление у мастера':'Автоматика разрешена'}</p>
      <p className="muted">Автоматика разрешается только для будущих входящих сообщений. Режим AI не означает, что ИИ уже подключён или ответит клиенту.</p>
      {view.state.manual_delivery.has_dispatching&&<p role="status">Отправка уже начата. Смена режима не отзывает внешний запрос.</p>}
      {view.state.manual_delivery.has_unknown&&<p role="status">Есть отправка с неизвестным результатом (UNKNOWN). Она не отменена и не отправляется повторно.</p>}
    </>}
    <div className="control-actions"><button disabled={!view.state||view.busy||!!p||manualPending()} onClick={()=>start('TAKEOVER')}>Забрать управление</button><button className="secondary" disabled={!view.state||view.busy||!!p||manualPending()} onClick={()=>start('RESUME')}>Разрешить автоматику</button></div>
    {view.notice&&<p role="status">{view.notice}</p>}
    {matching&&p&&<div className="notice" aria-live="polite">
      {p.phase==='sending'&&<p>Принимаем операцию… Новые действия заблокированы.</p>}
      {p.phase==='confirmed'&&<><p>Операция подтверждена. Повторяется только чтение режима.</p><button disabled={view.busy} onClick={()=>void read()}>Повторить чтение режима</button></>}
      {p.phase==='uncertain'&&<><p>Результат изменения режима неизвестен. Исходная операция сохранена в памяти страницы.</p>{session===p.failedSession?<button onClick={recover}>Проверить сессию для операции</button>:<button disabled={view.busy||manualPending()} onClick={()=>void send(p)}>Повторить исходную операцию</button>}</>}
      {p.phase==='conflict'&&<p role="alert">Конфликтующее намерение требует ручного завершения.</p>}
      {p.phase!=='sending'&&p.phase!=='confirmed'&&<button className="secondary" onClick={discard}>Завершить операцию без повтора</button>}
    </div>}
  </section>:null;
  return <>{p&&!matching&&<section className="panel alert" aria-label="Незавершённое управление"><p>В прежнем контексте осталось намерение изменения режима. Оно не переносится и не отправляется здесь.</p><p>Завершение ожидания не отменяет возможную серверную операцию.</p><button onClick={discard}>Завершить операцию без повтора</button></section>}{children?children(control,!!p):control}</>;
}
