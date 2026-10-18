import { FormEvent, MutableRefObject, ReactNode, useEffect, useRef, useState } from 'react';
import { Session } from './api';
import { ControlContext } from './conversation-control-api';
import { ContextBlocker, Disposition, HumanContextError, HumanContextState, ObservationPage, ReconcileBody, SourceMedia, humanContextApi, reconcileBody, serializeReconcile } from './human-context-api';

export type HumanContextIntent = ControlContext & {readonly actor:string;readonly body:ReconcileBody;readonly key:string;phase:'sending'|'uncertain'|'confirmed'|'blocked';ambiguous:boolean;failedSession:Session};
const blockers:Record<ContextBlocker|'HUMAN_REQUIRED',string>={POLICY_INACTIVE:'Сверка контекста ещё не включена оператором.',POLICY_PAUSED:'Автоматика приостановлена оператором. Контекст можно сверять и сохранять.',CONTEXT_CONFIRMATION_REQUIRED:'Нужно подтвердить доступный контекст.',CONTEXT_CHANGED:'Диалог изменился. Сверьте контекст заново.',CONTEXT_UNRESOLVED:'Есть неразрешённые вопросы.',NEW_OBSERVATION:'В канале замечены новые изменения.',CONTEXT_INPUT_UNRESOLVED:'Часть входящих данных не обработана или недоступна.',CONTEXT_COVERAGE_REQUIRED:'Доступной истории недостаточно: нужен полный текст владельца.',CONTEXT_INPUT_PENDING:'Входящие данные ещё обрабатываются.',HUMAN_REQUIRED:'Сначала заберите управление.'};
const coverageLabels={UNCONFIRMED:'Контекст не подтверждён',UNRESOLVED:'Контекст пока не разрешён',OWNER_TEXT:'Полный текст владельца',CANONICAL_COMPLETE:'Доступной истории достаточно по утверждению владельца',CANONICAL_TRUNCATED:'Доступная история ограничена'};
const reviewLabels:Record<HumanContextState['review_status'],string>={POLICY_INACTIVE:'Сверка ещё не включена',POLICY_PAUSED:'Новые разрешения автоматики приостановлены',BOOTSTRAP_REQUIRED:'Нужно первое подтверждение владельца',CONFIRMATION_REQUIRED:'Нужно новое подтверждение владельца',UNRESOLVED:'Существенные вопросы остаются неразрешёнными',NEW_OBSERVATION:'После сверки замечены новые изменения',INPUT_UNRESOLVED:'Есть неразрешённые входящие данные',COVERAGE_REQUIRED:'Нужен полный контекст владельца',INPUT_PENDING:'Входящие данные ещё обрабатываются',CONFIRMED:'Доступный контекст сверен'};
const workReasons:Record<Exclude<HumanContextState['automation_work']['reason'],null>,string>={CONTEXT_POLICY_PAUSED:'Политика приостановлена оператором.',CONTEXT_CONFIRMATION_REQUIRED:'Нужно новое подтверждение контекста.',CONTEXT_UNRESOLVED:'Контекст оставлен неразрешённым.',NEW_OBSERVATION:'После сверки есть новые наблюдения.',CONTEXT_INPUT_UNRESOLVED:'Входящие данные требуют проверки.',CONTEXT_COVERAGE_REQUIRED:'Доступной истории недостаточно.',CONTEXT_TOO_LARGE:'Объём контекста превышает предел обработки.',CONTEXT_WAIT_EXHAUSTED:'Предел ожидания обработки исчерпан.',CONTEXT_INPUT_PENDING:'Ожидается обработка входящих данных.'};
type View={generation:number;state:HumanContextState|null;busy:boolean;pages:ObservationPage[];pagesBusy:boolean;error:string;pageError:string;notice:string;draft:string;disposition:Disposition;media:SourceMedia;attested:boolean;replacement:boolean;denied:boolean};
const blank=(generation:number):View=>({generation,state:null,busy:false,pages:[],pagesBusy:false,error:'',pageError:'',notice:'',draft:'',disposition:'OWNER_TEXT',media:'NONE',attested:false,replacement:false,denied:false});
const readFailure='Не удалось прочитать сверенный контекст. Повторите чтение.';
export function HumanContextPanel({session,context,intent:provided,blocked=()=>false,refresh=0,accepted=()=>{},recover,expired,accessDenied,children}:{session:Session|null;context:ControlContext|null;intent?:MutableRefObject<HumanContextIntent|null>;blocked?:()=>boolean;refresh?:number;accepted?:()=>void;recover:()=>void;expired:()=>void;accessDenied:()=>void;children?:(panel:ReactNode,pending:boolean,state:HumanContextState|null)=>ReactNode}){
  const local=useRef<HumanContextIntent|null>(null),intent=provided??local;
  const owner=!!session&&!!context&&session.memberships.some(m=>m.workspace_id===context.workspace&&m.role==='OWNER');
  const scope=useRef({session,workspace:context?.workspace,conversation:context?.conversation,client:context?.client,owner,generation:0});
  if(scope.current.session!==session||scope.current.workspace!==context?.workspace||scope.current.conversation!==context?.conversation||scope.current.client!==context?.client||scope.current.owner!==owner)scope.current={session,workspace:context?.workspace,conversation:context?.conversation,client:context?.client,owner,generation:scope.current.generation+1};
  const generation=scope.current.generation,[stored,setView]=useState<View>(()=>blank(generation)),view=stored.generation===generation?stored:blank(generation);
  const [,redraw]=useState(0),alive=useRef(true),denied=useRef(-1),reading=useRef({state:false,pages:false}),sequence=useRef({state:0,pages:0}),controllers=useRef(new Set<AbortController>());
  const current=()=>alive.current&&scope.current.generation===generation&&scope.current.owner&&denied.current!==generation;
  const matches=(p:HumanContextIntent)=>p.actor===session?.user_account_id&&p.workspace===context?.workspace&&p.conversation===context?.conversation&&p.client===context?.client;
  const update=(patch:Partial<View>)=>{if(current())setView(v=>({...v,...patch}));};
  const changed=()=>redraw(n=>n+1);
  const controller=()=>{const c=new AbortController();controllers.current.add(c);return c;};
  function interrupt(){if(intent.current?.phase==='sending'){intent.current.phase='uncertain';intent.current.ambiguous=true;}}
  function authorization(e:unknown){
    if(!(e instanceof HumanContextError))return false;
    if(e.status===401&&e.code==='SESSION_REQUIRED'){interrupt();expired();return true;}
    if(e.status===403&&e.code==='CSRF_REJECTED'){interrupt();recover();return true;}
    if(e.status===403){interrupt();denied.current=generation;controllers.current.forEach(c=>c.abort());setView({...blank(generation),denied:true});accessDenied();return true;}
    return false;
  }
  async function read(){
    if(!context||!current()||reading.current.state||intent.current?.phase==='sending')return;
    const confirmed=intent.current?.phase==='confirmed'&&matches(intent.current)?intent.current:null,seq=++sequence.current.state,c=controller();
    reading.current.state=true;update({state:null,busy:true,error:'',attested:false,replacement:false});
    try{
      const state=await humanContextApi.read(context,c.signal);if(!current()||seq!==sequence.current.state)return;
      update({state,busy:false,...(!intent.current||confirmed?{draft:state.current_revision?.text??'',disposition:state.current_revision?.disposition??'OWNER_TEXT',media:state.current_revision?.source_media??'NONE'}:{})});
      if(confirmed&&intent.current===confirmed){intent.current=null;changed();update({notice:'Сохранение подтверждено. Показан текущий контекст; автоматика отдельно.'});}
    }catch(e){if(!current()||seq!==sequence.current.state)return;update({busy:false,error:readFailure});authorization(e);}
    finally{controllers.current.delete(c);if(current()&&seq===sequence.current.state)reading.current.state=false;}
  }
  async function observations(cursor:string|null=null){
    if(!context||!current()||reading.current.pages)return;
    const seq=++sequence.current.pages,c=controller();let stale=false;reading.current.pages=true;update({pagesBusy:true,pageError:'',attested:false,...(cursor===null?{pages:[]}:{} )});
    try{const page=await humanContextApi.observations(context,cursor,c.signal);if(!current()||seq!==sequence.current.pages)return;setView(v=>({...v,pages:cursor===null?[page]:[...v.pages,page],pagesBusy:false}));}
    catch(e){if(!current()||seq!==sequence.current.pages)return;stale=cursor!==null&&e instanceof HumanContextError&&e.code==='CONTEXT_CURSOR_STALE';update({pagesBusy:false,pageError:stale?'Условия просмотра изменились. Загружаем наблюдения с начала.':'Не удалось прочитать наблюдения. Повторите чтение.'});authorization(e);}
    finally{controllers.current.delete(c);if(current()&&seq===sequence.current.pages){reading.current.pages=false;if(stale)void observations();}}
  }
  function refreshReads(){sequence.current.state++;sequence.current.pages++;reading.current={state:false,pages:false};update({attested:false,replacement:false});void read();void observations();}
  useEffect(()=>{alive.current=true;interrupt();reading.current={state:false,pages:false};sequence.current.state++;sequence.current.pages++;setView(blank(generation));if(owner){void read();void observations();}return()=>{alive.current=false;interrupt();controllers.current.forEach(c=>c.abort());controllers.current.clear();};},[generation]);
  const refreshed=useRef(refresh);useEffect(()=>{if(refreshed.current!==refresh){refreshed.current=refresh;refreshReads();}},[refresh]);
  async function send(p:HumanContextIntent){
    if(!session||!context||!current()||!matches(p)||intent.current!==p||blocked()||reading.current.state||p.phase!=='uncertain')return;
    p.phase='sending';p.failedSession=session;changed();update({state:null,notice:'',error:'',attested:false,replacement:false});const c=controller();
    try{await humanContextApi.reconcile(p,p.body,p.key,session.csrf_token,c.signal);if(!current()||intent.current!==p)return;p.phase='confirmed';changed();update({notice:'Сервер подтвердил сохранение. Проверяем текущий контекст.'});accepted();void read();void observations();}
    catch(e){if(!current()||intent.current!==p)return;p.phase='uncertain';changed();if(e instanceof HumanContextError&&[401,403].includes(e.status)){p.ambiguous=true;if(authorization(e))return;}
      const definitive=e instanceof HumanContextError&&[404,409,413,415,422,429].includes(e.status);
      if(definitive){p.phase='blocked';update({notice:p.ambiguous?'Повтор остановлен. Попытка отклонена, но прежний результат остаётся неизвестным.':'Состояние изменилось или сохранение отклонено. Прочитайте текущий контекст и сделайте новый явный выбор.'});void read();void observations();}else p.ambiguous=true;
    }finally{controllers.current.delete(c);}
  }
  let candidate:ReconcileBody|null=null,size:number|null=null,inputError='';
  if(view.state){try{candidate=reconcileBody(view.state,view.disposition,view.disposition==='CANONICAL_SUFFICIENT'?null:view.draft===''?null:view.draft,view.disposition==='CANONICAL_SUFFICIENT'?'NONE':view.media);size=new TextEncoder().encode(serializeReconcile(candidate)).length;}catch(e){inputError=e instanceof HumanContextError&&e.code==='BODY_TOO_LARGE'?'Запись превышает 4096 байт. Сократите текст.':'Введите непустой текст без NUL и одиночных суррогатов, до 4096 символов Unicode.';}}
  function submit(e:FormEvent){e.preventDefault();if(!session||!context||!current()||!view.state||!candidate||inputError||!view.attested||!view.replacement||view.busy||reading.current.state||intent.current||blocked()||view.state.policy==='OFF_UNUSED'||view.state.control_mode!=='HUMAN'||view.state.pending_context_input)return;
    const p:HumanContextIntent={actor:session.user_account_id,...context,body:candidate,key:crypto.randomUUID(),phase:'uncertain',ambiguous:false,failedSession:session};intent.current=p;void send(p);
  }
  function discard(){if(intent.current?.phase==='sending'&&matches(intent.current))return;intent.current=null;changed();update({notice:'Ожидание завершено. Возможное серверное сохранение не отменено.'});refreshReads();}
  const p=intent.current,attached=!!p&&matches(p)&&owner&&!view.denied,s=view.state,last=view.pages.at(-1);
  const panel=owner&&!view.denied?<section className="human-context" aria-label="Сверка контекста">
    <div className="billing-heading"><h3>Контекст владельца</h3><button className="secondary" disabled={view.busy||p?.phase==='sending'} onClick={refreshReads}>Обновить контекст</button></div>
    <p>Перед обсуждением в Telegram заберите управление. Наблюдения канала — сигнал, а не доказанная договорённость владельца. Даже отсутствие обновлений не доказывает полноту или порядок внешней истории.</p>
    {view.busy&&<p role="status">Читаем текущий контекст…</p>}{view.error&&<p role="alert">{view.error}</p>}
    {s&&<>
      <p role="status">{s.policy==='OFF_UNUSED'?'Сверка ещё не включена оператором':s.policy==='PAUSED'?'Автоматика приостановлена оператором':'Сверка контекста включена'}</p>
      <p>{coverageLabels[s.coverage_status]}</p>
      <p aria-label="Состояние сверки">{reviewLabels[s.review_status]}</p>
      <ul aria-label="Что требует проверки">{s.context_blockers.map(b=><li key={b}>{blockers[b]}</li>)}</ul>
      <ul aria-label="Перед разрешением автоматики">{s.resume_blockers.map(b=><li key={b}>{blockers[b]}</li>)}</ul>
      <p role="status">{s.automation_work.state==='IDLE'?'Нет текущей отметки работы с контекстом. Это не доказывает, что старый запрос клиента получил ответ.':s.automation_work.state==='WAITING_CONTEXT'?'Автоматика ожидает обработки входящих данных.':'Для остановленной работы нужен оператор. Сверка не перезапускает и не повторяет отправку.'}</p>
      {s.automation_work.reason!==null&&<p>{workReasons[s.automation_work.reason]}</p>}
      {s.manual_delivery.has_dispatching&&<p>Ручная отправка уже начата; её нельзя отозвать сменой режима.</p>}{s.manual_delivery.has_unknown&&<p>Есть ручная отправка UNKNOWN. Её результат неизвестен; повторной отправки нет.</p>}
      <section aria-label="Сохранённый контекст"><h4>Текущий сохранённый контекст</h4>{s.current_revision?<><p>{s.current_revision.disposition==='OWNER_TEXT'?'Утверждение владельца':s.current_revision.disposition==='CANONICAL_SUFFICIENT'?'Владелец подтвердил доступную историю':'Вопросы остаются неразрешёнными'}</p>{s.current_revision.text!==null&&<p className="exact-answer">{s.current_revision.text}</p>}<p>{s.current_revision.actor_user_account_id===session?.user_account_id?'Сверили вы':'Сверил другой владелец'} · <time dateTime={s.current_revision.accepted_at}>{s.current_revision.accepted_at}</time></p>{s.current_revision.source_media==='UNAVAILABLE'&&<p>Исходное изображение или содержимое недоступно. Текстовое описание не делает его доступным.</p>}</>:<p>Подтверждения ещё нет.</p>}</section>
      <form className="form" onSubmit={submit}>
        <label>Результат сверки<select aria-label="Результат сверки" disabled={!!p} value={view.disposition} onChange={e=>update({disposition:e.target.value as Disposition,attested:false,replacement:false})}><option value="OWNER_TEXT">Полный актуальный текст владельца</option><option value="CANONICAL_SUFFICIENT">Доступной истории достаточно</option><option value="UNRESOLVED">Оставить неразрешённым</option></select></label>
        {view.disposition!=='CANONICAL_SUFFICIENT'&&<label>Новый полный контекст<textarea aria-label="Новый полный контекст" rows={5} value={attached&&p?p.body.text??'':view.draft} disabled={!!p} onChange={e=>update({draft:e.target.value,attested:false,replacement:false})}/></label>}
        {view.disposition==='CANONICAL_SUFFICIENT'?<p>Текст владельца будет отозван. Сервер заново проверит достаточность доступной истории.</p>:<label>Исходные изображения<select aria-label="Исходные изображения" value={view.media} disabled={!!p} onChange={e=>update({media:e.target.value as SourceMedia,attested:false})}><option value="NONE">Нет известного недоступного содержимого</option><option value="UNAVAILABLE">Есть недоступное фото или содержимое</option></select></label>}
        <p>Это полная замена прежнего контекста. Неуказанные старые факты не добавляются обратно. Если существенные факты не помещаются, оставьте контекст неразрешённым. Текст владельца не подтверждает полноту Telegram и не даёт права отправки.</p>
        {size!==null&&<p>Размер записи: {size} из 4096 байт.</p>}{inputError&&<p role="alert">{inputError}</p>}
        <label><input type="checkbox" checked={view.replacement} disabled={!!p} onChange={e=>update({replacement:e.target.checked})}/>Подтверждаю полную замену или отзыв прежнего контекста</label>
        <label><input type="checkbox" checked={view.attested} disabled={!!p} onChange={e=>update({attested:e.target.checked})}/>Я сверил доступный контекст и существенные договорённости</label>
        <button disabled={!!p||blocked()||view.busy||!view.attested||!view.replacement||!!inputError||s.policy==='OFF_UNUSED'||s.control_mode!=='HUMAN'||s.pending_context_input}>Сохранить сверенный контекст</button>
      </form>
      <p>Сохранение не разрешает автоматику, не меняет управление и не отправляет сообщение. «Разрешить автоматику» — отдельное действие после свежей проверки.</p>
    </>}
    <section aria-label="Наблюдения канала"><h4>Наблюдения провайдера</h4><p>Это доступные сигналы, а не полная история или подтверждение авторства. Просмотр страниц не является сверкой.</p>
      <button className="secondary" disabled={view.pagesBusy} onClick={()=>void observations()}>Обновить наблюдения</button>{view.pagesBusy&&<p role="status">Читаем наблюдения…</p>}{view.pageError&&<p role="alert">{view.pageError}</p>}
      <ol>{view.pages.flatMap(page=>page.items).map(o=><li key={o.observation_id}><time>{o.observed_at}</time><p>{o.source_kind==='EDIT'?'Наблюдалось изменение в канале':o.source_kind==='DELETE'?'Наблюдалось удаление в канале':'Наблюдалось сообщение в канале'}</p>{o.preview.kind==='TEXT'?<p className="exact-answer">{o.preview.text}</p>:o.preview.kind==='PHOTO'?<><p>Фото недоступно для просмотра.</p>{o.preview.caption!==null&&<p className="exact-answer">{o.preview.caption}</p>}</>:o.preview.kind==='DELETE'?<p>Наблюдалось удаление сообщений: {o.preview.target_count}.</p>:<p>{o.preview.reason==='AMBIGUOUS_ORIGIN'?'Происхождение сообщения неоднозначно.':o.preview.reason==='UNSUPPORTED_CONTENT'?'Тип содержимого не поддерживается.':'Содержимое наблюдения недоступно.'}</p>}</li>)}</ol>
      {last?.next_cursor&&<button disabled={view.pagesBusy} onClick={()=>void observations(last.next_cursor)}>Ещё наблюдения</button>}{last&&last.next_cursor===null&&<p>Конец доступного среза наблюдений.</p>}{last&&last.current_epoch!==last.through_epoch&&<p>Есть новые наблюдения. Обновите контекст и наблюдения перед сохранением.</p>}
    </section>
    {view.notice&&<p role="status">{view.notice}</p>}
    {attached&&p&&<div className="notice" aria-live="polite">{p.phase==='sending'?<p>Сохраняем контекст…</p>:p.phase==='confirmed'?<><p>Сохранение подтверждено. Повторяется только чтение.</p><button disabled={view.busy} onClick={()=>void read()}>Повторить чтение контекста</button></>:p.phase==='blocked'?<p>Повтор остановлен. Завершите ожидание и сделайте новый явный выбор.</p>:<><p>Результат сохранения неизвестен. Исходное намерение остаётся в памяти страницы.</p>{session===p.failedSession?<button onClick={recover}>Проверить сессию для контекста</button>:<button disabled={view.busy||blocked()} onClick={()=>void send(p)}>Повторить исходное сохранение контекста</button>}</>}{p.phase!=='sending'&&p.phase!=='confirmed'&&<button onClick={discard}>Завершить ожидание контекста без повтора</button>}</div>}
  </section>:null;
  return <>{p&&!attached&&<section className="panel alert" aria-label="Незавершённая сверка"><p>В прежнем контексте осталось намерение сверки. Здесь его содержимое не показывается и не отправляется.</p><button onClick={discard}>Завершить ожидание контекста без повтора</button></section>}{children?children(panel,!!p,view.denied?null:view.state):panel}</>;
}
