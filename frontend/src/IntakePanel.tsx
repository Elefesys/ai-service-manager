import {useEffect,useId,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {Session} from './api';
import {priceAmount} from './configuration-api';
import {approvalApi,draftApprovalSelection,EscalationError} from './escalation-api';
import type {ApprovalSelection} from './escalation-api';
import {IntakeError,intakeApi,labels} from './intake-api';
import type {CaseMatch,DraftCommand,DraftListItem,DraftRevisionCommand,Fact,FieldId,Intake,IntakeScope,PriceCalculation,PriceHistory,ServiceAssessment,ServiceRequestDraft} from './intake-api';

export function IntakePanel({session,scope,expired,refresh=0,approvalOpened}:{session:Session|null;scope:IntakeScope|null;expired:()=>void;refresh?:number;approvalOpened?:(selection:ApprovalSelection)=>void}){
 const key=scope?JSON.stringify({...scope,refresh}):'',current=useRef({key,session,epoch:0});
 if(current.current.key!==key||current.current.session!==session)current.current={key,session,epoch:current.current.epoch+1};
 const [view,setView]=useState<{key:string;session:Session|null;value:Intake|null;error:string;busy:boolean}>({key:'',session:null,value:null,error:'',busy:false});
 const [summaryRefresh,setSummaryRefresh]=useState(0);
 const [comparisons,setComparisons]=useState<{key:string;session:Session|null;fingerprint:string;items:CaseMatch[];busy:boolean;error:string}>({key:'',session:null,fingerprint:'',items:[],busy:false,error:''});
 const [edits,setEdits]=useState<Record<string,string>>({});const controls=useRef(new Set<AbortController>());
 const intent=useRef<{key:string;scope:IntakeScope;operation:string;body:unknown}|null>(null);
 const visible=view.key===key&&view.session===session;const data=visible?view.value:null;
 const permitted=!!session&&!!scope&&session.memberships.some(m=>m.workspace_id===scope.workspace&&m.role==='OWNER');
 async function load(){if(!permitted||!scope)return;const epoch=current.current.epoch,c=new AbortController();controls.current.add(c);setSummaryRefresh(n=>n+1);setView({key,session,value:null,error:'',busy:true});
 try{const value=await intakeApi.summary(scope,c.signal);if(c.signal.aborted||epoch!==current.current.epoch)return;setView({key,session,value,error:'',busy:false});setEdits({});}catch(e){if(!c.signal.aborted&&epoch===current.current.epoch){setView({key,session,value:null,error:'Не удалось получить актуальную сводку.',busy:false});if(e instanceof IntakeError&&e.status===401)expired();}}finally{controls.current.delete(c);}}
 useEffect(()=>{intent.current=null;setEdits({});void load();return()=>{current.current.epoch++;controls.current.forEach(c=>c.abort());controls.current.clear();};},[key,session]);
 async function save(fact:Fact){if(!scope||!session||!data||view.busy||intent.current)return;const value=edits[fact.field]??fact.value;intent.current={key:crypto.randomUUID(),scope,operation:value===fact.value?'confirm':'correct',body:{expected_version:data.version,expected_fingerprint:data.fingerprint,field:fact.field,value,source:fact.source}};await send();}
 async function send(){const p=intent.current;if(!p||!session||JSON.stringify({...p.scope,refresh})!==key)return;const epoch=current.current.epoch,c=new AbortController();controls.current.add(c);setView(v=>({...v,busy:true,error:''}));try{await intakeApi.command(p.scope,p.operation,p.body,p.key,session.csrf_token,c.signal);if(c.signal.aborted||epoch!==current.current.epoch)return;intent.current=null;await load();}catch(e){if(c.signal.aborted||epoch!==current.current.epoch)return;if(e instanceof IntakeError&&[403,404,409,422].includes(e.status)){intent.current=null;setView({key,session,value:null,busy:false,error:'Сводка изменилась или команда недоступна. Обновите сведения.'});}else setView(v=>({...v,busy:false,error:'Результат команды неизвестен. Можно проверить ту же команду.'}));if(e instanceof IntakeError&&e.status===401)expired();}finally{controls.current.delete(c);}}
 async function compare(){if(!scope||!session||!data)return;const epoch=current.current.epoch,fingerprint=data.fingerprint,c=new AbortController();controls.current.add(c);setComparisons({key,session,fingerprint,items:[],busy:true,error:''});const query=Object.fromEntries(data.facts.filter(f=>['placement','style'].includes(f.field)&&!f.conflict).map(f=>[f.field,f.value]));try{const result=await intakeApi.search(scope,query,c.signal);if(!c.signal.aborted&&epoch===current.current.epoch)setComparisons({key,session,fingerprint,items:result.items,busy:false,error:''});}catch(e){if(!c.signal.aborted&&epoch===current.current.epoch){setComparisons({key,session,fingerprint,items:[],busy:false,error:'Не удалось получить текущие подтверждённые примеры.'});if(e instanceof IntakeError&&e.status===401)expired();}}finally{controls.current.delete(c);}}
 const compared=!!data&&comparisons.key===key&&comparisons.session===session&&comparisons.fingerprint===data.fingerprint;
 if(!permitted||!scope||!session)return null;
 const draftScopeKey=JSON.stringify([scope.workspace,scope.business,scope.conversation,scope.client,session.user_account_id,session.csrf_token]);
 return <section className="intake-card" aria-label="Предварительный запрос"><div className="billing-heading"><h3>Предварительный запрос</h3><button className="secondary" onClick={()=>void load()} disabled={visible&&view.busy}>Обновить сводку</button></div><p>Мастер проверяет детали. Цена, длительность и запись ещё не согласованы.</p>{visible&&view.error&&<p role="alert">{view.error}</p>}{intent.current&&visible&&!view.busy&&<button onClick={()=>void send()}>Проверить ту же команду</button>}{data&&<><p role="status">{({NOT_STARTED:'Сбор ещё не начат',CLARIFY:'Нужно уточнение',OWNER_HANDOFF:'Требуется решение мастера',PRELIMINARILY_COMPLETE:'Предварительно собрано'})[data.status]}</p>{data.question&&<p>{data.question}</p>}{data.facts.map(f=><article key={f.field}><label>{labels[f.field]}<input disabled={view.busy||!!intent.current} maxLength={300} value={edits[f.field]??f.value} onChange={e=>setEdits(v=>({...v,[f.field]:e.target.value}))}/></label><p>{f.status==='owner-confirmed'?'Подтверждено мастером':f.status==='observed'?'Наблюдение изображения':'Со слов клиента'}{f.conflict?' · есть противоречие':''}</p><p className="muted">Источник: <a href={`#message-${f.source.message_id}`}>сообщение клиента</a> · {f.source.quote||'текущий анализ изображения'}</p><button disabled={view.busy||!!intent.current||!(edits[f.field]??f.value).trim()} onClick={()=>void save(f)}>Подтвердить поле {labels[f.field]}</button></article>)}{data.missing.length>0&&<p>Неизвестно: {data.missing.map(f=>labels[f]).join(', ')}</p>}<button className="secondary" disabled={compared&&comparisons.busy} onClick={()=>void compare()}>Сравнить с примерами мастера</button>{compared&&<div aria-label="Сравнение примеров мастера"><p>Время прошлых работ видно только мастеру. Это не оценка нового запроса.</p>{comparisons.error&&<p role="alert">{comparisons.error}</p>}{!comparisons.busy&&!comparisons.error&&comparisons.items.length===0&&<p>Подтверждённых текущих примеров нет.</p>}{comparisons.items.map(m=><article key={m.case.case_id}><h4>{m.case.data.description}</h4><p>Совпадает: {m.matches.map(f=>labels[f]??f).join(', ')||'нет'} · различается: {m.differences.map(f=>labels[f]??f).join(', ')||'нет'} · неизвестно: {m.unknown.map(f=>labels[f]??f).join(', ')||'нет'}</p><p>Источник: подтверждённый пример, версия {m.case.version}. Рабочее время: {m.case.data.working_minutes??'неизвестно'}, занятое: {m.case.data.occupied_minutes??'неизвестно'} мин.</p></article>)}</div>}</>}{scope.conversation&&
  <RequestDraftPanel key={draftScopeKey} selectionScope={draftScopeKey} scope={scope} data={data} summaryRefresh={summaryRefresh} csrf={session.csrf_token} expired={expired} approvalOpened={approvalOpened}/>
 }</section>;
}

type DraftChoice={fingerprint:string;messageId:string;fields:FieldId[];confirmed:boolean};
type RevisionChoice={fingerprint:string;confirmed:boolean}&(
 {field:FieldId}|{field:'complex_work';messageId:string}
);
type DraftAttempt={key:string;acceptedId?:string}&(
 {operation:'create';body:DraftCommand}|{operation:'revise';target:string;body:DraftRevisionCommand}
);

async function selectionKey(scope:string){
 try{
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(`asm:draft-selection:v1:${scope}`));
  return `asm:draft-selection:${Array.from(new Uint8Array(bytes),byte=>byte.toString(16).padStart(2,'0')).join('')}`;
 }catch{return null;}
}

function storedRequest(key:string|null){
 try{
  const value=key?sessionStorage.getItem(key):null;
  return value&&/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value)&&value.length===36?value:undefined;
 }catch{return undefined;}
}

function rememberRequest(key:string|null,id?:string){
 if(!key)return;
 try{if(id)sessionStorage.setItem(key,id);else sessionStorage.removeItem(key);}catch{/* Selection is optional. */}
}

function draftError(error:IntakeError):string{
 switch(error.code){
  case 'NEEDS_CLARIFICATION':return 'Уточните, к какой работе относятся выбранное начало и сведения.';
  case 'STALE_STATE':return 'Заявка или сводка изменились. Обновите карточку заявки и сводку, затем снова выберите сведения.';
  case 'IDEMPOTENCY_KEY_CONFLICT':return 'Команда с этим ключом уже сохранена с другими сведениями. Обновите сводку.';
  default:return 'Команда для этой заявки недоступна.';
 }
}

function factStatus(fact:Fact){
 if(fact.status==='owner-confirmed')return 'Подтверждено мастером';
 return fact.status==='observed'?'Наблюдение изображения':'Со слов клиента';
}

function DraftCard({draft,children}:{draft:ServiceRequestDraft;children:ReactNode}){
 return <section aria-label="Черновик заявки">
  <h4>Черновик заявки</h4>
  <article>
   <dl>
    <dt>ID заявки</dt><dd><code data-testid="service-request-id">{draft.request_id}</code></dd>
    <dt>Услуга</dt><dd>{draft.service_name}</dd>
    <dt>Ревизия</dt><dd data-testid="service-request-revision">{draft.revision}</dd>
    <dt>Начало работы</dt><dd>
     <a href={`#message-${draft.intent_source.message_id}`}>Исходное сообщение</a> · версия <code>{draft.intent_source.source_version}</code>
    </dd>
   </dl>
   {draft.facts.map(fact=><div key={fact.field}>
    <p><strong>{labels[fact.field]}</strong> · {fact.value} · {factStatus(fact)}{fact.conflict?' · есть противоречие':''}</p>
    <p>Источник: <a href={`#message-${fact.source.message_id}`}>Сообщение для поля {labels[fact.field]}</a> · версия <code>{fact.source.source_version}</code></p>
    {fact.source.analysis_id&&<p>Анализ <code>{fact.source.analysis_id}</code> · SHA-256 <code>{fact.source.analysis_sha256}</code></p>}
   </div>)}
   {draft.missing.length>0&&<p>Не хватает: {draft.missing.map(field=>labels[field]).join(', ')}</p>}
   {draft.conflicts.length>0&&<p>Противоречия: {draft.conflicts.map(field=>labels[field]).join(', ')}</p>}
   {draft.question&&<p>{draft.question}</p>}
  </article>
  {children}
 </section>;
}

const assessmentLabels:Record<ServiceAssessment['outcome'],string>={
 FEASIBLE:'Выполнимо',NEEDS_DATA:'Нужны данные',NEEDS_OWNER:'Решает мастер',DECLINED:'Отказ',
};

function assessmentReason(value:ServiceAssessment):string{
 const field=value.field?` «${labels[value.field]}»`:'';
 switch(value.reason){
  case 'FIXED_DURATION':return 'Фиксированная длительность из опубликованных настроек.';
  case 'SIZE_DURATION_RULE':return 'Опубликованное правило длительности по размеру.';
  case 'MISSING_FACT':return value.field==='approximate_size'?'Какой примерный размер вы представляете, в сантиметрах?':`Уточните сведение${field}.`;
  case 'CONFLICTING_FACT':return `Уточните противоречивое сведение${field}.`;
  case 'SOURCE_CHANGED':return `Проверьте текущий источник сведения${field} и обновите заявку.`;
  case 'SIZE_NEEDS_CONFIRMATION':return 'Подтвердите размер в сантиметрах или миллиметрах.';
  case 'MIN_AGE_UNCONFIRMED':return 'Уточните возраст для проверки опубликованного ограничения.';
  case 'SIZE_LIMIT_EXCEEDED':return value.size_mm!==null&&value.limit!==null
   ?`Размер ${value.size_mm} мм превышает опубликованный предел ${value.limit} мм.`:'Размер превышает опубликованный предел.';
  case 'OWNER_HANDOFF':return 'Мастер проверяет возможность выполнения этой работы.';
  case 'OWNER_DURATION':return 'Мастер задаёт длительность следующего сеанса.';
  case 'SERVICE_UNAVAILABLE':return 'Опубликованная услуга для этой заявки недоступна.';
  case 'DURATION_UNPUBLISHED':return 'Опубликуйте настройку длительности или передайте выбор мастеру.';
 }
}

function AssessmentPanel({scope,draft,csrf,activation,locked,expired}:{scope:IntakeScope;draft:ServiceRequestDraft;csrf:string;activation?:string;locked:boolean;expired:()=>void}){
 const [value,setValue]=useState<ServiceAssessment|null>(null);
 const [busy,setBusy]=useState(true);
 const [error,setError]=useState('');
 const [retry,setRetry]=useState(false);
 const [blocked,setBlocked]=useState(false);
 const active=useRef<AbortController|null>(null);

 async function load(evaluate:boolean){
  if(active.current)return;
  const controller=new AbortController(),{signal}=controller;
  active.current=controller;
  setBusy(true);setError('');setRetry(false);
  try{
   const result=evaluate
    ?await intakeApi.assess(scope,draft.request_id,draft.revision,csrf,signal)
    :await intakeApi.assessment(scope,draft.request_id,signal);
   if(signal.aborted)return;
   setValue(result);setBlocked(false);
  }catch(failure){
   if(signal.aborted)return;
   setValue(previous=>previous?{...previous,current:false}:previous);
   if(failure instanceof IntakeError&&[401,403,404].includes(failure.status)){
    setValue(null);setBlocked(true);setError('Оценка заявки недоступна.');
    if(failure.status===401)expired();
   }else if(failure instanceof IntakeError&&failure.code==='STALE_STATE'){
    setBlocked(true);setError('Заявка изменилась. Обновите карточку заявки и пересчитайте оценку.');
   }else{
    setRetry(evaluate);setError(evaluate?'Результат оценки неизвестен. Повторите оценку заявки.':'Не удалось получить оценку заявки.');
   }
  }finally{
   if(active.current===controller){active.current=null;if(!signal.aborted)setBusy(false);}
  }
 }

 useEffect(()=>{
  void load(false);
  return ()=>{active.current?.abort();active.current=null;};
 },[draft]);

 const current=!!value&&value.current&&value.request_revision===draft.revision&&!busy
  &&(activation===undefined||BigInt(activation)<=BigInt(value.activation_version));
 return <section aria-label="Оценка заявки" style={{overflowWrap:'anywhere'}}>
  <h4>Оценка заявки</h4>
  {error&&<p role="alert">{error}</p>}
  {value&&<article>
   <p>{current?assessmentLabels[value.outcome]:busy?'Проверяем актуальность оценки':'Архивная оценка. Для актуального результата выполните пересчёт.'}</p>
   {current&&<p>{assessmentReason(value)}</p>}
   {current&&value.occupied_minutes!==null&&<>
    <p>Занято на следующий сеанс <strong>{value.occupied_minutes} мин</strong>.</p>
    <p>Занятость включает подготовку внутри сеанса. Внешние буферы учитываются отдельно.</p>
   </>}
   {!current&&!busy&&value.occupied_minutes!==null&&<p>Ранее было утверждено {value.occupied_minutes} мин.</p>}
   {current&&value.complex_work&&<p>
    {value.complex_work.category==='COVER_UP'?'Перекрытие старой татуировки.':'Работа требует индивидуальной оценки.'}{' '}
    <a href={`#message-${value.complex_work.source.message_id}`}>Сообщение с уточнением</a> · версия <code>{value.complex_work.source.source_version}</code>
    {!value.complex_work.source_current&&' · источник изменился, проверьте уточнение.'}
   </p>}
   {value.release_id&&<p>Публикация <code>{value.release_id}</code> · версия активации {value.activation_version}</p>}
   {current&&value.duration_policy?.size_rule&&<p>Порог опубликованного правила {value.duration_policy.size_rule.threshold_mm} мм.</p>}
   {current&&value.size_mm!==null&&value.reason!=='SIZE_LIMIT_EXCEEDED'&&<p>Размер для оценки {value.size_mm} мм.</p>}
   {value.rule_id&&<p>Правило <code>{value.rule_id}</code></p>}
   {value.evidence.length>0&&<ul>
    {value.evidence.map(fact=><li key={fact.field}>
     {labels[fact.field]} · {fact.value} · {factStatus(fact)}{fact.conflict?' · есть противоречие':''} · <a href={`#message-${fact.source.message_id}`}>Источник оценки для поля {labels[fact.field]}</a> · версия <code>{fact.source.source_version}</code>
     {fact.source.analysis_id&&<> · анализ <code>{fact.source.analysis_id}</code> · SHA-256 <code>{fact.source.analysis_sha256}</code></>}
    </li>)}
   </ul>}
   {value.archived_duration&&<details>
    <summary>Архивная оценка</summary>
    <p>Ревизия {value.archived_duration.request_revision} · ранее было утверждено {value.archived_duration.occupied_minutes} мин.</p>
    {value.archived_duration.release_id&&<p>Публикация <code>{value.archived_duration.release_id}</code> · версия активации {value.archived_duration.activation_version}</p>}
   </details>}
  </article>}
  <div className="control-actions">
   <button type="button" disabled={busy||locked||blocked} onClick={()=>void load(true)}>{retry?'Повторить оценку заявки':value?'Пересчитать оценку':'Оценить заявку'}</button>
   <button type="button" className="secondary" disabled={busy||locked} onClick={()=>void load(false)}>Обновить оценку заявки</button>
  </div>
 </section>;
}

const pricingReasons:Record<PriceCalculation['reason'],string>={
 FIXED_PRICE:'Фиксированная цена из опубликованных настроек.',
 SIZE_FORMULA:'По опубликованной формуле размера.',
 SIZE_REQUIRED:'Уточните подтверждённый размер в миллиметрах.',
 SIZE_OUTSIDE_RULE:'Размер выходит за предел опубликованной формулы.',
 OWNER_QUOTE:'Режим цены этой услуги задан мастером.',
 PRICE_UNPUBLISHED:'Для услуги нужна опубликованная цена или поддерживаемая формула.',
 SERVICE_UNAVAILABLE:'Опубликованная услуга для этой заявки недоступна.',
};
function PriceResult({value}:{value:PriceCalculation}){
 const rule=value.policy?.size_formula;
 return <>
  {value.outcome==='EXACT'&&value.amount_minor!==null&&<p>Подтверждённая цена <strong>{priceAmount(value.amount_minor)}</strong></p>}
  {value.outcome==='RANGE'&&value.lower_minor!==null&&value.upper_minor!==null&&<p>Предварительный диапазон <strong>{priceAmount(value.lower_minor)} – {priceAmount(value.upper_minor)}</strong></p>}
  {value.outcome==='NEEDS_HUMAN'&&<p>Цену определяет мастер</p>}
  <p>{value.reason==='SIZE_OUTSIDE_RULE'&&rule
   ?`Размер превышает опубликованный предел ${rule.max_size_mm} мм.`:pricingReasons[value.reason]}</p>
  {value.size_fact&&<p>
   Размер {value.reason==='SIZE_OUTSIDE_RULE'?value.size_fact.value:`${value.size_mm} мм`} · <a href={`#message-${value.size_fact.source.message_id}`}>Источник размера для цены</a>{' '}
   · версия <code>{value.size_fact.source.source_version}</code>
  </p>}
  {rule&&value.steps!==null&&<p>
   {priceAmount(rule.base_minor)} + {value.steps} × {priceAmount(rule.step_minor)} · шаг {rule.step_mm} мм, округление вверх.
   {rule.range_add_minor!==null&&` Верхняя граница включает ещё ${priceAmount(rule.range_add_minor)}.`}
  </p>}
  {value.release_id&&<p>Публикация <code>{value.release_id}</code> · версия активации {value.activation_version}{rule?' · SIZE_STEPS_V1':''}</p>}
 </>;
}
function PricingPanel({scope,draft,csrf,activation,summaryRefresh,locked,expired}:{scope:IntakeScope;draft:ServiceRequestDraft;csrf:string;activation?:string;summaryRefresh:number;locked:boolean;expired:()=>void}){
 const [history,setHistory]=useState<PriceHistory>({items:[],next_before_id:null});
 const [calculation,setCalculation]=useState<PriceCalculation|null>(null);
 const [checkedRefresh,setCheckedRefresh]=useState<number|null>(null);
 const [busy,setBusy]=useState(true);
 const [error,setError]=useState('');
 const [blocked,setBlocked]=useState(false);
 const active=useRef<AbortController|null>(null);

 async function load(calculate=false,beforeId?:string){
  if(active.current)return;
  const controller=new AbortController(),{signal}=controller;
  active.current=controller;
  setBusy(true);setError('');
  try{
   if(calculate)await intakeApi.calculatePrice(scope,draft.request_id,draft.revision,csrf,signal);
   const latest=await intakeApi.priceHistory(scope,draft.request_id,beforeId,signal);
   if(signal.aborted)return;
   if(beforeId){
    setHistory(previous=>({items:[...previous.items,...latest.items],next_before_id:latest.next_before_id}));
   }else{
    setCalculation(latest.items.find(item=>item.current)??null);
    setHistory({items:latest.items.filter(item=>!item.current),next_before_id:latest.next_before_id});
    setCheckedRefresh(summaryRefresh);
   }
   setBlocked(false);
  }catch(failure){
   if(signal.aborted)return;
   if(failure instanceof IntakeError&&[401,403,404].includes(failure.status)){
    setCalculation(null);setHistory({items:[],next_before_id:null});setBlocked(true);
    setError('Расчёт цены недоступен.');
    if(failure.status===401)expired();
   }else if(failure instanceof IntakeError&&failure.code==='STALE_STATE'){
    setCalculation(null);setBlocked(true);setError('Заявка изменилась. Обновите карточку перед расчётом цены.');
   }else{
    setCalculation(previous=>previous?{...previous,current:false}:previous);
    setError(calculate?'Не удалось прочитать результат. Повторите расчёт цены.':'Не удалось прочитать историю расчётов.');
   }
  }finally{
   if(active.current===controller){active.current=null;if(!signal.aborted)setBusy(false);}
  }
 }

 useEffect(()=>{
  void load();
  return ()=>{active.current?.abort();active.current=null;};
 },[draft,summaryRefresh]);

 const checked=checkedRefresh===summaryRefresh;
 const current=checked&&calculation?.current&&calculation.request_revision===draft.revision
  &&(activation===undefined||BigInt(activation)<=BigInt(calculation.activation_version));
 const archived=checked&&calculation&&!current?[calculation,...history.items]:history.items;
 return <section aria-label="Расчёт цены" style={{overflowWrap:'anywhere'}}>
  <h4>Расчёт цены</h4>
  {error&&<p role="alert">{error}</p>}
  {current&&calculation&&<article aria-label="Текущий расчёт цены"><PriceResult value={calculation}/></article>}
  {!current&&archived.length>0&&<p>Обновите расчёт, чтобы получить актуальную цену.</p>}
  {archived.length>0&&<details>
   <summary>История расчётов цены</summary>
   {archived.map(item=><article key={item.calculation_id} aria-label="Архивный расчёт цены">
    <p>Архив · ревизия заявки {item.request_revision}</p>
    <PriceResult value={item}/>
   </article>)}
   {history.next_before_id&&<button type="button" className="secondary" disabled={busy||locked} onClick={()=>void load(false,history.next_before_id!)}>Показать предыдущие расчёты</button>}
  </details>}
  <div className="control-actions">
   <button type="button" disabled={busy||locked||blocked} onClick={()=>void load(true)}>
    {current||archived.length>0?'Пересчитать цену':'Рассчитать цену'}
   </button>
   <button type="button" className="secondary" disabled={busy||locked} onClick={()=>void load()}>Обновить расчёт цены</button>
  </div>
 </section>;
}

function sourceLabel(source:Intake['sources'][number]){
 return `${Array.from(source.text.trim()).slice(0,100).join('')||'Входящее фото'} · #${source.message_id.slice(-6)}`;
}

function OpenOwnerApproval({scope,draft,csrf,locked,expired,opened}:{scope:IntakeScope;draft:ServiceRequestDraft;csrf:string;locked:boolean;expired:()=>void;opened:(selection:ApprovalSelection)=>void}){
 const active=useRef<AbortController|null>(null);
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 useEffect(()=>()=>active.current?.abort(),[]);
 async function open(){
  if(active.current||locked)return;
  const controller=new AbortController();
  active.current=controller;setBusy(true);setNotice('');
  try{
   const result=await approvalApi.open(approvalApi.scope(scope,draft.request_id),draft.revision,csrf,controller.signal);
   if(controller.signal.aborted)return;
   if(result)opened(draftApprovalSelection(result));
   else setNotice('Цена и длительность уже утверждены.');
  }catch(error){
   if(controller.signal.aborted)return;
   if(error instanceof EscalationError&&error.status===401)expired();
   else setNotice('Не удалось открыть решение. Обновите карточку заявки и повторите.');
  }finally{if(!controller.signal.aborted){setBusy(false);active.current=null;}}
 }
 return <div className="control-actions">
  <button type="button" disabled={locked||busy} onClick={()=>void open()}>Открыть решение мастера</button>
  {notice&&<p role="status">{notice}</p>}
 </div>;
}

function RequestDraftPanel({scope,selectionScope,data,summaryRefresh,csrf,expired,approvalOpened}:{scope:IntakeScope;selectionScope:string;data:Intake|null;summaryRefresh:number;csrf:string;expired:()=>void;approvalOpened?:(selection:ApprovalSelection)=>void}){
 const sourceId=useId();
 const cardId=useId();
 const revisionFieldId=useId();
 const revisionMessageId=useId();
 const [draft,setDraft]=useState<ServiceRequestDraft|null>(null);
 const [cards,setCards]=useState<DraftListItem[]>([]);
 const [choice,setChoice]=useState<DraftChoice|null>(null);
 const [revisionChoice,setRevisionChoice]=useState<RevisionChoice|null>(null);
 const [busy,setBusy]=useState(true);
 const [readable,setReadable]=useState(false);
 const [revisionNeedsRead,setRevisionNeedsRead]=useState(false);
 const [error,setError]=useState('');
 const active=useRef<AbortController|null>(null);
 const pending=useRef<DraftAttempt|null>(null);
 const storeKey=useRef<string|null>(null);
 const desiredCard=useRef<string|undefined>(undefined);

 async function open(requestId?:string,attempt?:DraftAttempt){
  if(active.current)return;
  const controller=new AbortController();
  active.current=controller;
  const signal=controller.signal;
  let target=requestId;
  setBusy(true);
  setError('');
  try{
   if(attempt){
    if(!attempt.acceptedId){
     const receipt=attempt.operation==='create'
      ?await intakeApi.saveDraft(scope,attempt.body,attempt.key,csrf,signal)
      :await intakeApi.reviseDraft(scope,attempt.target,attempt.body,attempt.key,csrf,signal);
     if(signal.aborted)return;
     attempt.acceptedId=receipt.request_id;
    }
    target=attempt.acceptedId;
   }
   desiredCard.current=target;
   const [result,items]=await Promise.all([intakeApi.draft(scope,target,signal),intakeApi.drafts(scope,signal)]);
   if(signal.aborted)return;
   setDraft(result);
   setCards(items);
   setReadable(true);
   setChoice(null);
   setRevisionChoice(null);
   setRevisionNeedsRead(false);
   pending.current=null;
   desiredCard.current=result?.request_id;
   rememberRequest(storeKey.current,result?.request_id);
  }catch(failure){
   if(signal.aborted)return;
   if(failure instanceof IntakeError&&[400,401,403,404,409,422].includes(failure.status)){
    const clarifyCreate=attempt?.operation==='create'&&!attempt.acceptedId&&failure.status===409&&failure.code==='NEEDS_CLARIFICATION';
    pending.current=null;
    setChoice(selected=>clarifyCreate&&selected?{...selected,confirmed:false}:null);
    setRevisionChoice(null);
    setError(clarifyCreate
     ?'Проверьте, к какой работе относятся выбранные сведения. Снимите отметку со спорного поля и подтвердите выбор ещё раз.'
     :draftError(failure));
    if(attempt?.operation==='revise'&&failure.code==='STALE_STATE')setRevisionNeedsRead(true);
    if([401,403,404].includes(failure.status)){
     setDraft(null);setCards([]);setReadable(false);
     desiredCard.current=undefined;
     rememberRequest(storeKey.current);
    }
    if(failure.status===401)expired();
   }else if(attempt){
    setError(attempt.acceptedId?'Заявка сохранена. Карточку можно открыть повторно.':
     attempt.operation==='create'?'Результат создания неизвестен. Можно повторить ту же команду.':'Результат изменения неизвестен. Можно повторить ту же команду.');
   }else{
    setError('Не удалось открыть заявку.');
   }
  }finally{
   if(active.current===controller){
    active.current=null;
    if(!signal.aborted)setBusy(false);
   }
  }
 }

 // The parent key is the exact authenticated conversation, independent of intake refresh.
 useEffect(()=>{
  let mounted=true;
  void selectionKey(selectionScope).then(key=>{
   if(!mounted)return;
   storeKey.current=key;
   void open(storedRequest(key));
  });
  return()=>{mounted=false;active.current?.abort();active.current=null;pending.current=null;};
 },[]);

 const canChoose=data?.template_revision==='tattoo_intake_v1'&&!!data.service_id
  &&data.category!=='AMBIGUOUS'&&data.category!=='FAQ_ONLY';
 const beginnings=data?.sources.filter(item=>!cards.some(card=>card.intent_source.message_id===item.message_id))??[];
 const selected=choice?.fingerprint===data?.fingerprint?choice:null;
 const sourceIndex=data?.sources.findIndex(source=>source.message_id===selected?.messageId)??-1;
 const source=beginnings.find(item=>item.message_id===selected?.messageId);
 const eligible=source&&data?data.facts.filter(fact=>data.sources.findIndex(item=>
  item.message_id===fact.source.message_id&&item.source_version===fact.source.source_version)>=sourceIndex):[];
 const canRevise=canChoose&&data&&draft?.service_id===data.service_id&&draft.template_revision===data.template_revision;
 const revisionSources=canRevise?data.sources.filter(item=>!cards.some(card=>
  card.request_id!==draft.request_id&&card.intent_source.message_id===item.message_id)):[];
 const revisionFacts=canRevise?data.facts.filter(fact=>!fact.conflict&&!data.conflicts.includes(fact.field)
  &&revisionSources.some(item=>item.message_id===fact.source.message_id&&item.source_version===fact.source.source_version)):[];
 const hasComplexity=data?.category==='COVER_UP'||data?.category==='OTHER_COMPLEX';
 const revision=revisionChoice?.fingerprint===data?.fingerprint?revisionChoice:null;
 const revisionFact=revisionFacts.find(fact=>fact.field===revision?.field);
 const revisionSource=revision?.field==='complex_work'
  ?revisionSources.find(item=>item.message_id===revision.messageId)
  :revisionSources.find(item=>item.message_id===revisionFact?.source.message_id&&item.source_version===revisionFact?.source.source_version);
 const waiting=pending.current;
 const locked=busy||!!waiting;

 function startCreate(){
  if(!data||!source||!selected?.confirmed||locked||!canChoose||pending.current)return;
  const attempt:DraftAttempt={operation:'create',key:crypto.randomUUID(),body:{
   expected_version:data.version,
   expected_fingerprint:data.fingerprint,
   intent_source:{message_id:source.message_id,source_version:source.source_version},
   fields:eligible.filter(fact=>selected.fields.includes(fact.field)).map(fact=>fact.field),
   selection:'ONE_WORK',
  }};
  pending.current=attempt;
  void open(undefined,attempt);
 }

 function startRevision(){
  if(!data||!draft||!revisionSource||!revision?.confirmed||locked||revisionNeedsRead||pending.current)return;
  const attempt:DraftAttempt={operation:'revise',target:draft.request_id,key:crypto.randomUUID(),body:{
   expected_revision:draft.revision,expected_version:data.version,expected_fingerprint:data.fingerprint,
   ...(revisionFact?{field:revisionFact.field}:{}),
   source:{message_id:revisionSource.message_id,source_version:revisionSource.source_version},selection:'ONE_WORK',
  }};
  pending.current=attempt;
  void open(draft.request_id,attempt);
 }

 return <>
  {cards.length>0&&<section aria-label="Заявки диалога">
   <label htmlFor={cardId}>Сохранённая заявка</label>
   <select id={cardId} value={draft?.request_id??''} disabled={locked} onChange={event=>{
    const id=event.target.value;
    if(id&&id!==draft?.request_id){setDraft(null);setRevisionChoice(null);void open(id);}
   }}>
    <option value="" disabled>Выберите заявку</option>
    {cards.map(card=><option key={card.request_id} value={card.request_id}>
     {card.idea||card.service_name} · #{card.request_id.slice(-6)}
    </option>)}
   </select>
  </section>}
  {draft&&<DraftCard draft={draft}>
   <AssessmentPanel key={`${draft.request_id}:${draft.revision}`} scope={scope} draft={draft} csrf={csrf} activation={data?.activation_version} locked={locked} expired={expired}/>
   <PricingPanel key={`price:${draft.request_id}:${draft.revision}`} scope={scope} draft={draft} csrf={csrf} activation={data?.activation_version} summaryRefresh={summaryRefresh} locked={locked} expired={expired}/>
   {approvalOpened&&scope.conversation&&scope.client&&<OpenOwnerApproval key={'approval:'+draft.request_id+':'+draft.revision} scope={scope} draft={draft} csrf={csrf} locked={locked} expired={expired} opened={approvalOpened}/>}
  </DraftCard>}
  {error&&<p role="alert">{error}</p>}
  {waiting&&!busy&&<button type="button" onClick={()=>void open(desiredCard.current,waiting)}>
   {waiting.acceptedId?'Открыть сохранённую заявку':waiting.operation==='create'?'Повторить создание заявки':'Повторить изменение заявки'}
  </button>}
  {!locked&&(draft||error)&&<button type="button" className="secondary" onClick={()=>void open(desiredCard.current)}>Обновить карточку заявки</button>}
  {(revisionFacts.length>0||hasComplexity&&revisionSources.length>0)&&data&&draft&&<fieldset aria-label="Уточнение заявки" disabled={locked||revisionNeedsRead} style={{minWidth:0}}>
   <label htmlFor={revisionFieldId}>Уточняемое сведение</label>
   <select id={revisionFieldId} value={revision?.field??''} onChange={event=>{
    const field=event.target.value;
    const next={fingerprint:data.fingerprint,confirmed:false};
    setRevisionChoice(field==='complex_work'?{...next,field,messageId:''}:
     field?{...next,field:field as FieldId}:null);
   }}>
    <option value="">Выберите одно сведение</option>
    {revisionFacts.map(fact=><option key={fact.field} value={fact.field}>{labels[fact.field]}: {fact.value}</option>)}
    <option value="complex_work">Сообщение о сложности</option>
   </select>
   {revision?.field==='complex_work'&&<>
    <label htmlFor={revisionMessageId}>Сообщение о сложности</label>
    <select id={revisionMessageId} value={revision.messageId} style={{maxWidth:'100%'}} onChange={event=>setRevisionChoice({
     ...revision,messageId:event.target.value,confirmed:false,
    })}>
     <option value="">Выберите сообщение о сложности</option>
     {revisionSources.map(item=><option key={item.message_id} value={item.message_id}>{sourceLabel(item)}</option>)}
    </select>
   </>}
   {revisionSource&&revision&&<>
    <p style={{overflowWrap:'anywhere'}}>
     <a href={`#message-${revisionSource.message_id}`}>Сообщение для уточнения</a> · {sourceLabel(revisionSource)} · версия <code>{revisionSource.source_version}</code>
    </p>
    <label style={{display:'block'}}>
     <input type="checkbox" checked={revision.confirmed} onChange={event=>setRevisionChoice({...revision,confirmed:event.target.checked})}/>
     {revision.field==='complex_work'?'Сообщение о сложности относится к выбранной заявке':'Сведение из этого сообщения относится к выбранной заявке'}
    </label>
   </>}
   <button type="button" onClick={startRevision} disabled={!revisionSource||!revision?.confirmed}>Сохранить уточнение заявки</button>
  </fieldset>}
  {readable&&canChoose&&data&&beginnings.length>0&&<fieldset aria-label="Выбор сведений для заявки" disabled={locked} style={{minWidth:0}}>
   <label htmlFor={sourceId}>Начало работы</label>
   <select id={sourceId} value={source?.message_id??''} style={{maxWidth:'100%'}} onChange={event=>setChoice({
    fingerprint:data.fingerprint,messageId:event.target.value,fields:[],confirmed:false,
   })}>
    <option value="">Выберите исходное сообщение</option>
    {beginnings.map(item=><option key={item.message_id} value={item.message_id}>{sourceLabel(item)}</option>)}
   </select>
   {selected&&source&&<>
    <p>Выберите сведения об одной работе. Если их принадлежность неясна, уточните её у клиента.</p>
    {eligible.map(fact=><label key={fact.field} style={{display:'block'}}>
     <input type="checkbox" checked={selected.fields.includes(fact.field)} onChange={event=>setChoice({
      ...selected,confirmed:false,fields:event.target.checked?[...selected.fields,fact.field]:selected.fields.filter(field=>field!==fact.field),
     })}/>
     {labels[fact.field]}: {fact.value}
    </label>)}
    <label style={{display:'block'}}>
     <input type="checkbox" checked={selected.confirmed} onChange={event=>setChoice({...selected,confirmed:event.target.checked})}/>
     Начало и выбранные сведения относятся к одной работе
    </label>
   </>}
   <button type="button" onClick={startCreate} disabled={!source||!selected?.confirmed}>Создать заявку</button>
  </fieldset>}
 </>;
}
