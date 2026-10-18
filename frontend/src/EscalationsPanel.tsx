import { FormEvent, useEffect, useRef, useState } from 'react';
import { Session } from './api';
import { EscalationBody, EscalationContext, EscalationError, EscalationOperation, EscalationPage, EscalationView, StatusFilter, escalationApi, exactAnswer } from './escalation-api';

type Intent = {
  readonly actor: string; readonly context: EscalationContext; readonly operation: EscalationOperation; readonly body: EscalationBody; readonly key: string;
  phase: 'sending' | 'uncertain' | 'confirmed' | 'blocked'; ambiguous: boolean; failedSession: Session;
};
type View = { generation: number; filter: StatusFilter; pages: EscalationPage[]; listed: boolean; listBusy: boolean; listError: string; selected: EscalationContext|null; detail: EscalationView|null; detailBusy: boolean; detailError: string; answer: string; notice: string; denied: boolean };
const blank = (generation: number): View => ({generation,filter:'PENDING',pages:[],listed:false,listBusy:false,listError:'',selected:null,detail:null,detailBusy:false,detailError:'',answer:'',notice:'',denied:false});
const statusLabel: Record<StatusFilter,string> = {PENDING:'Открытые',RESOLVED:'С ответом',CANCELLED:'Отменённые',EXPIRED:'Истёкшие',ALL:'Все'};
const validityLabel: Record<EscalationView['validity'],string> = {CURRENT:'Запрос актуален',CONTROL_CHANGED:'Управление изменилось',CONTEXT_CHANGED:'Контекст диалога изменился',ASSIGNEE_REVOKED:'Ответственный потерял доступ владельца',EXPIRED:'Срок истёк',TERMINAL:'Запрос завершён'};
const closureLabel: Record<NonNullable<EscalationView['closure']>['reason'],string> = {OWNER_CANCELLED:'Отменён владельцем',CONTROL_CHANGED:'Изменилось управление',CONTEXT_CHANGED:'Изменился контекст',ASSIGNEE_REVOKED:'Ответственный потерял доступ',DEADLINE_ELAPSED:'Истёк срок'};
const contextOf = (v: EscalationView): EscalationContext => ({workspace:v.workspace_id,escalation:v.escalation_id,conversation:v.conversation_id,client:v.client_id});
const failure = (e: unknown) => e instanceof EscalationError&&e.code==='RATE_LIMITED'?'Слишком много запросов. Повторите позже.':e instanceof EscalationError&&e.code==='NOT_FOUND'?'Запрос не найден или недоступен.':e instanceof EscalationError&&e.code==='INVALID_REQUEST'?'Страница недоступна. Обновите очередь с начала.':'Не удалось прочитать запросы. Повторите чтение.';

// Mounted for the page lifetime, including auth recovery. No storage or effects
// that POST. The ref synchronously freezes one intention before double submit.
export function EscalationsPanel({session,workspace,recover,expired,accessDenied,accepted}: {
  session: Session|null; workspace: string; recover: ()=>void; expired: ()=>void; accessDenied: ()=>void; accepted?: (context: EscalationContext)=>void;
}) {
  const owner=!!session&&session.memberships.some(m=>m.workspace_id===workspace&&m.role==='OWNER');
  const scope=useRef({session,workspace,owner,generation:0});
  const selection=useRef<{context: EscalationContext|null; epoch: number}>({context:null,epoch:0});
  if(scope.current.session!==session||scope.current.workspace!==workspace||scope.current.owner!==owner){
    scope.current={session,workspace,owner,generation:scope.current.generation+1};
    selection.current={context:null,epoch:selection.current.epoch+1};
  }
  const generation=scope.current.generation;
  const [stored,setView]=useState<View>(()=>blank(generation));
  const view=stored.generation===generation?stored:blank(generation);
  const intent=useRef<Intent|null>(null), alive=useRef(true), denied=useRef(-1);
  const filter=useRef<StatusFilter>('PENDING'), sequence=useRef({list:0,detail:0}), reading=useRef({list:false,detail:false});
  const controllers=useRef(new Set<AbortController>());
  const [,redraw]=useState(0);
  const current=()=>alive.current&&scope.current.generation===generation&&scope.current.owner&&denied.current!==generation;
  const sameActor=(p:Intent)=>p.actor===session?.user_account_id&&p.context.workspace===workspace;
  const inDetail=(context:EscalationContext,epoch:number)=>current()&&selection.current.epoch===epoch&&selection.current.context?.escalation===context.escalation;
  const matching=(p:Intent)=>sameActor(p)&&selection.current.context?.escalation===p.context.escalation;
  const changed=()=>redraw(n=>n+1);
  const update=(patch:Partial<View>)=>{if(current())setView(v=>({...v,...patch}));};
  const controller=()=>{const c=new AbortController();controllers.current.add(c);return c;};
  function interrupt(){if(intent.current?.phase==='sending'){intent.current.phase='uncertain';intent.current.ambiguous=true;}}
  function authorization(e:unknown){
    if(!(e instanceof EscalationError))return false;
    if(e.status===401&&e.code==='SESSION_REQUIRED'){interrupt();expired();return true;}
    if(e.status===403&&e.code==='CSRF_REJECTED'){interrupt();recover();return true;}
    if(e.status===403){interrupt();denied.current=generation;controllers.current.forEach(c=>c.abort());setView({...blank(generation),denied:true});accessDenied();return true;}
    return false;
  }
  async function list(cursor:string|null=null, supersede=false){
    if(!current()||(reading.current.list&&!supersede))return;
    const seq=++sequence.current.list,c=controller(),status=filter.current;
    reading.current.list=true;
    update({...(cursor===null?{pages:[],listed:false}:{}),listBusy:true,listError:''});
    try {
      const page=await escalationApi.list(workspace,status,cursor,c.signal);
      if(!current()||seq!==sequence.current.list)return;
      setView(v=>({...v,pages:cursor===null?[page]:[...v.pages,page],listed:true,listBusy:false}));
    } catch(e){if(!current()||seq!==sequence.current.list)return;if(!authorization(e))update({listBusy:false,listError:failure(e)});}
    finally {controllers.current.delete(c);if(current()&&seq===sequence.current.list)reading.current.list=false;}
  }
  async function read(context=selection.current.context){
    if(!context||!current()||reading.current.detail||intent.current?.phase==='sending')return;
    const epoch=selection.current.epoch,seq=++sequence.current.detail,c=controller();
    const confirmed=intent.current?.phase==='confirmed'&&matching(intent.current)?intent.current:null;
    reading.current.detail=true;update({detail:null,detailBusy:true,detailError:''});
    try {
      const detail=await escalationApi.read(context,c.signal);
      if(!inDetail(context,epoch)||seq!==sequence.current.detail)return;
      update({detail,detailBusy:false});
      if(confirmed&&intent.current===confirmed){intent.current=null;changed();update({notice:'Решение сохранено. Актуальная карточка получена.'});}
    } catch(e){if(!inDetail(context,epoch)||seq!==sequence.current.detail)return;if(!authorization(e))update({detail:null,detailBusy:false,detailError:failure(e)});}
    finally {controllers.current.delete(c);if(inDetail(context,epoch)&&seq===sequence.current.detail)reading.current.detail=false;}
  }
  function choose(context:EscalationContext|null){
    if(!current())return;
    interrupt();selection.current={context,epoch:selection.current.epoch+1};sequence.current.detail++;reading.current.detail=false;
    update({selected:context,detail:null,detailBusy:false,detailError:'',answer:'',notice:''});
    if(context)void read(context);
  }
  useEffect(()=>{
    alive.current=true;interrupt();filter.current='PENDING';reading.current={list:false,detail:false};sequence.current.list++;sequence.current.detail++;setView(blank(generation));
    if(owner){void list();const p=intent.current;if(p&&sameActor(p))choose(p.context);}
    return ()=>{alive.current=false;interrupt();controllers.current.forEach(c=>c.abort());controllers.current.clear();};
  },[generation]);
  function selectFilter(value:StatusFilter){filter.current=value;choose(null);update({filter:value});void list(null,true);}
  async function send(p:Intent){
    if(!session||!current()||intent.current!==p||!matching(p)||reading.current.detail||p.phase!=='uncertain')return;
    const epoch=selection.current.epoch,c=controller();p.phase='sending';p.failedSession=session;changed();update({detail:null,notice:'',detailError:'',answer:''});
    try {
      await escalationApi.command(p.context,p.operation,p.body,p.key,session.csrf_token,c.signal);
      if(!inDetail(p.context,epoch)||intent.current!==p)return;
      p.phase='confirmed';changed();update({notice:'Решение подтверждено сервером. Оно не отправлено клиенту.'});
      accepted?.(p.context);void list(null,true);void read();
    } catch(e){
      if(!inDetail(p.context,epoch)||intent.current!==p)return;
      p.phase='uncertain';changed();
      if(e instanceof EscalationError&&[401,403].includes(e.status)){p.ambiguous=true;if(authorization(e))return;}
      const definitive=e instanceof EscalationError&&[404,409,413,415,422,429].includes(e.status);
      if(definitive){
        p.phase='blocked';
        update({notice:p.ambiguous?'Повтор остановлен. Эта попытка отклонена; исходный результат всё ещё неизвестен.':'Решение отклонено: запрос изменился, завершён или недоступен. Прочитайте карточку и примите новое решение.'});
        void list(null,true);void read();
      } else {p.ambiguous=true;}
    } finally {controllers.current.delete(c);}
  }
  function start(operation:EscalationOperation,event?:FormEvent){
    event?.preventDefault();const d=view.detail;
    if(!session||!current()||!d||intent.current||reading.current.detail||!view.selected)return;
    if(operation==='RESOLVE'&&(!d.can_resolve||d.assignee_user_account_id!==session.user_account_id)||operation==='CANCEL'&&!d.can_cancel)return;
    if(operation==='RESOLVE'){try{exactAnswer(view.answer);}catch{update({notice:'Введите 1–512 символов Unicode, не только пробелы, без NUL и одиночных суррогатов (до 2048 байт UTF-8).'});return;}}
    const body:EscalationBody=Object.freeze({expected_conversation_id:d.conversation_id,expected_client_id:d.client_id,expected_escalation_version:d.version,expected_control_generation:d.current_context.control_generation,expected_context_version:d.current_context.context_version,...(operation==='RESOLVE'?{answer_text:view.answer}:{})});
    const p:Intent={actor:session.user_account_id,context:Object.freeze(contextOf(d)),operation,body,key:crypto.randomUUID(),phase:'uncertain',ambiguous:false,failedSession:session};
    intent.current=p;void send(p);
  }
  function discard(){
    if(intent.current?.phase==='sending'&&matching(intent.current))return;
    intent.current=null;changed();update({answer:'',notice:'Локальное ожидание завершено. Возможная серверная операция не отменена.'});void read();void list(null,true);
  }
  const p=intent.current,attached=!!p&&owner&&!view.denied&&matching(p);
  const last=view.pages.at(-1),d=view.detail;
  // Each item retains its own page clock; pages do not form a frozen snapshot.
  const seen=new Set<string>();
  return <>
    {p&&!attached&&<section className="panel alert" aria-label="Незавершённое решение"><p>В прежнем контексте осталось намерение решения. Здесь оно не показывается и не отправляется.</p><p>Завершение ожидания не отменяет возможную серверную операцию.</p><button onClick={discard}>Завершить ожидание решения</button></section>}
    {owner&&(view.denied?<section className="panel alert" role="alert"><p>Нет доступа к запросам владельца.</p><button onClick={recover}>Проверить доступ к запросам</button></section>:<section className="panel escalations" aria-label="Запросы владельцу">
      <div className="billing-heading"><div><span className="kicker">OWNER</span><h2>Запросы владельцу</h2></div><button className="secondary" disabled={view.listBusy} onClick={()=>void list()}>Обновить очередь</button></div>
      <p className="muted">Внутренние решения по выбранному Workspace. Ответ здесь не отправляется клиенту и не включает автоматику.</p>
      <label htmlFor="escalation-filter">Сохранённый статус</label><select id="escalation-filter" value={view.filter} onChange={e=>selectFilter(e.target.value as StatusFilter)}>{Object.entries(statusLabel).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select>
      {view.listBusy&&<p role="status">Загружаем очередь…</p>}{view.listError&&<p role="alert">{view.listError}</p>}
      {view.listed&&!view.pages.some(page=>page.items.length)&&<p>Запросов с этим статусом нет.</p>}
      <ul className="escalation-list">{view.pages.flatMap(page=>page.items.map(item=>{
        if(seen.has(item.escalation_id))return null;seen.add(item.escalation_id);
        return <li key={item.escalation_id}><button className="secondary" data-testid={`escalation-${item.escalation_id}`} aria-pressed={view.selected?.escalation===item.escalation_id} onClick={()=>choose(contextOf(item))}><strong>Требуется решение владельца</strong><span>{statusLabel[item.status]} · {validityLabel[item.validity]}</span><span>Ответственный: {item.assignee_user_account_id===session?.user_account_id?'вы':item.assignee_user_account_id}</span><small>Создан: {item.created_at} · Срок: {item.expires_at}</small><small>Наблюдение страницы: {page.observed_at}</small></button></li>;
      }))}</ul>
      {last?.next_cursor&&<button disabled={view.listBusy} onClick={()=>void list(last.next_cursor)}>Ещё запросы</button>}
      {view.listed&&last?.next_cursor===null&&view.pages.some(page=>page.items.length>0)&&<p>Конец очереди на момент чтения. Новые запросы появятся после обновления.</p>}
      {view.selected&&<section className="escalation-detail" aria-label="Карточка запроса">
        <div className="billing-heading"><h3>Решение владельца</h3><button className="secondary" disabled={view.detailBusy||p?.phase==='sending'} onClick={()=>void read()}>Обновить запрос</button></div>
        {view.detailBusy&&<p role="status">Читаем актуальный запрос…</p>}{view.detailError&&<p role="alert">{view.detailError}</p>}
        {d&&<><p>{d.question}</p>{d.context_hold&&<p role="status">{d.context_hold.reason==='CONTEXT_POLICY_PAUSED'?'Сверка приостановлена оператором.':d.context_hold.reason==='CONTEXT_INPUT_PENDING'?'Входящий контекст ещё обрабатывается.':d.context_hold.reason==='CONTEXT_UNRESOLVED'?'Контекст оставлен неразрешённым.':d.context_hold.reason==='CONTEXT_COVERAGE_REQUIRED'?'Доступной истории недостаточно.':d.context_hold.reason==='NEW_OBSERVATION'?'Есть новые наблюдения канала.':'Контекст требует сверки владельцем.'} Сохранение ответа сейчас недоступно. Отмена определяется текущими правами сервера.</p>}<dl><dt>Сохранённый статус</dt><dd>{statusLabel[d.status]}</dd><dt>Текущая применимость</dt><dd>{validityLabel[d.validity]}</dd><dt>Ожидание</dt><dd>{d.waiting==='WAITING_FOR_HUMAN'?'Ожидается решение владельца':'Актуального ожидания нет'}</dd><dt>Ответственный</dt><dd>{d.assignee_user_account_id===session?.user_account_id?'Вы':d.assignee_user_account_id}</dd><dt>Создан</dt><dd>{d.created_at}</dd><dt>Срок запроса</dt><dd>{d.expires_at}</dd><dt>Состояние прочитано</dt><dd>{d.observed_at}</dd><dt>Режим при чтении</dt><dd>{d.current_context.control_mode==='HUMAN'?'Управление у мастера':'Сохранён режим AI'}</dd></dl>
          <p className="muted">Срок определяет сервер; это не обещание времени ответа клиенту.</p>
          <details><summary>Связанный диалог и клиент</summary><dl><dt>Запрос</dt><dd>{d.escalation_id}</dd><dt>Диалог</dt><dd>{d.conversation_id}</dd><dt>Клиент</dt><dd>{d.client_id}</dd></dl></details>
          <h4>Внутренние напоминания</h4><ul>{d.reminders.map(r=><li key={r.ordinal}>Напоминание {r.ordinal}: срок {r.due_at}; {r.recorded_at?`записано ${r.recorded_at}`:'запись отсутствует'}</li>)}</ul>
          <p className="muted">Запись напоминания не означает отправку уведомления или прочтение владельцем.</p>
          <p role={d.maintenance==='FAILED'?'alert':'status'}>{d.maintenance==='FAILED'?'Ошибка обслуживания напоминаний. Это не завершает запрос.':d.maintenance==='COMPLETE'?'Обслуживание напоминаний завершено.':'Обслуживание напоминаний запланировано.'}</p>
          {d.resolution&&<div><h4>Сохранённый внутренний ответ</h4><p className="exact-answer">{d.resolution.answer_text}</p><p>Сохранил: {d.resolution.actor_user_account_id} · {d.resolution.completed_at}</p></div>}
          {d.closure&&<p>{closureLabel[d.closure.reason]} · {d.closure.completed_at}{d.closure.actor_user_account_id?` · Владелец: ${d.closure.actor_user_account_id}`:''}</p>}
          <form onSubmit={e=>start('RESOLVE',e)}><label htmlFor="escalation-answer">Внутренний ответ владельца</label><textarea id="escalation-answer" value={view.answer} disabled={!!p||!d.can_resolve||d.assignee_user_account_id!==session?.user_account_id} onChange={e=>update({answer:e.target.value})} rows={3}/><div className="control-actions"><button type="submit" disabled={!!p||!d.can_resolve||d.assignee_user_account_id!==session?.user_account_id}>Сохранить внутренний ответ</button><button type="button" className="secondary" disabled={!!p||!d.can_cancel} onClick={()=>start('CANCEL')}>Отменить запрос</button></div></form>
        </>}
        {view.notice&&<p role="status">{view.notice}</p>}
        {attached&&p&&<div className="notice" aria-live="polite">
          {p.phase==='sending'&&<p>Сохраняем решение… Повторный submit заблокирован.</p>}
          {p.phase==='confirmed'&&<><p>Решение подтверждено. Повторяется только чтение.</p><button disabled={view.detailBusy} onClick={()=>{void read();void list(null,true);}}>Повторить чтение запроса</button></>}
          {p.phase==='uncertain'&&<><p>Результат решения неизвестен. Исходное намерение сохранено в памяти страницы.</p>{session===p.failedSession?<button onClick={recover}>Проверить сессию для решения</button>:<button disabled={view.detailBusy} onClick={()=>void send(p)}>Повторить исходное решение</button>}</>}
          {p.phase==='blocked'&&<p>Повтор решения остановлен. Для нового намерения завершите ожидание и проверьте свежую карточку.</p>}
          {p.phase!=='sending'&&p.phase!=='confirmed'&&<><p>Завершение ожидания не отменяет возможную серверную операцию.</p><button className="secondary" onClick={discard}>Завершить ожидание решения</button></>}
        </div>}
      </section>}
    </section>)}
  </>;
}
