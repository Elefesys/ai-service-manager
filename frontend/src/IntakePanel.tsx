import {useEffect,useId,useRef,useState} from 'react';
import {Session} from './api';
import {IntakeError,intakeApi,labels} from './intake-api';
import type {CaseMatch,DraftCommand,Fact,FieldId,Intake,IntakeScope,ServiceRequestDraft} from './intake-api';

export function IntakePanel({session,scope,expired,refresh=0}:{session:Session|null;scope:IntakeScope|null;expired:()=>void;refresh?:number}){
 const key=scope?JSON.stringify({...scope,refresh}):'',current=useRef({key,session,epoch:0});
 if(current.current.key!==key||current.current.session!==session)current.current={key,session,epoch:current.current.epoch+1};
 const [view,setView]=useState<{key:string;session:Session|null;value:Intake|null;error:string;busy:boolean}>({key:'',session:null,value:null,error:'',busy:false});
 const [comparisons,setComparisons]=useState<{key:string;session:Session|null;fingerprint:string;items:CaseMatch[];busy:boolean;error:string}>({key:'',session:null,fingerprint:'',items:[],busy:false,error:''});
 const [edits,setEdits]=useState<Record<string,string>>({});const controls=useRef(new Set<AbortController>());
 const intent=useRef<{key:string;scope:IntakeScope;operation:string;body:unknown}|null>(null);
 const visible=view.key===key&&view.session===session;const data=visible?view.value:null;
 const permitted=!!session&&!!scope&&session.memberships.some(m=>m.workspace_id===scope.workspace&&m.role==='OWNER');
 async function load(){if(!permitted||!scope)return;const epoch=current.current.epoch,c=new AbortController();controls.current.add(c);setView({key,session,value:null,error:'',busy:true});
 try{const value=await intakeApi.summary(scope,c.signal);if(c.signal.aborted||epoch!==current.current.epoch)return;setView({key,session,value,error:'',busy:false});setEdits({});}catch(e){if(!c.signal.aborted&&epoch===current.current.epoch){setView({key,session,value:null,error:'Не удалось получить актуальную сводку.',busy:false});if(e instanceof IntakeError&&e.status===401)expired();}}finally{controls.current.delete(c);}}
 useEffect(()=>{intent.current=null;setEdits({});void load();return()=>{current.current.epoch++;controls.current.forEach(c=>c.abort());controls.current.clear();};},[key,session]);
 async function save(fact:Fact){if(!scope||!session||!data||view.busy||intent.current)return;const value=edits[fact.field]??fact.value;intent.current={key:crypto.randomUUID(),scope,operation:value===fact.value?'confirm':'correct',body:{expected_version:data.version,expected_fingerprint:data.fingerprint,field:fact.field,value,source:fact.source}};await send();}
 async function send(){const p=intent.current;if(!p||!session||JSON.stringify({...p.scope,refresh})!==key)return;const epoch=current.current.epoch,c=new AbortController();controls.current.add(c);setView(v=>({...v,busy:true,error:''}));try{await intakeApi.command(p.scope,p.operation,p.body,p.key,session.csrf_token,c.signal);if(c.signal.aborted||epoch!==current.current.epoch)return;intent.current=null;await load();}catch(e){if(c.signal.aborted||epoch!==current.current.epoch)return;if(e instanceof IntakeError&&[403,404,409,422].includes(e.status)){intent.current=null;setView({key,session,value:null,busy:false,error:'Сводка изменилась или команда недоступна. Обновите сведения.'});}else setView(v=>({...v,busy:false,error:'Результат команды неизвестен. Можно проверить ту же команду.'}));if(e instanceof IntakeError&&e.status===401)expired();}finally{controls.current.delete(c);}}
 async function compare(){if(!scope||!session||!data)return;const epoch=current.current.epoch,fingerprint=data.fingerprint,c=new AbortController();controls.current.add(c);setComparisons({key,session,fingerprint,items:[],busy:true,error:''});const query=Object.fromEntries(data.facts.filter(f=>['placement','style'].includes(f.field)&&!f.conflict).map(f=>[f.field,f.value]));try{const result=await intakeApi.search(scope,query,c.signal);if(!c.signal.aborted&&epoch===current.current.epoch)setComparisons({key,session,fingerprint,items:result.items,busy:false,error:''});}catch(e){if(!c.signal.aborted&&epoch===current.current.epoch){setComparisons({key,session,fingerprint,items:[],busy:false,error:'Не удалось получить текущие подтверждённые примеры.'});if(e instanceof IntakeError&&e.status===401)expired();}}finally{controls.current.delete(c);}}
 const compared=!!data&&comparisons.key===key&&comparisons.session===session&&comparisons.fingerprint===data.fingerprint;
 if(!permitted||!scope||!session)return null;
 const draftScopeKey=JSON.stringify([scope.workspace,scope.business,scope.conversation,scope.client,session.user_account_id,session.csrf_token]);
 return <section className="intake-card" aria-label="Предварительный запрос"><div className="billing-heading"><h3>Предварительный запрос</h3><button className="secondary" onClick={()=>void load()} disabled={visible&&view.busy}>Обновить сводку</button></div><p>Мастер проверяет детали. Цена, длительность и запись ещё не согласованы.</p>{visible&&view.error&&<p role="alert">{view.error}</p>}{intent.current&&visible&&!view.busy&&<button onClick={()=>void send()}>Проверить ту же команду</button>}{data&&<><p role="status">{({NOT_STARTED:'Сбор ещё не начат',CLARIFY:'Нужно уточнение',OWNER_HANDOFF:'Требуется решение мастера',PRELIMINARILY_COMPLETE:'Предварительно собрано'})[data.status]}</p>{data.question&&<p>{data.question}</p>}{data.facts.map(f=><article key={f.field}><label>{labels[f.field]}<input disabled={view.busy||!!intent.current} maxLength={300} value={edits[f.field]??f.value} onChange={e=>setEdits(v=>({...v,[f.field]:e.target.value}))}/></label><p>{f.status==='owner-confirmed'?'Подтверждено мастером':f.status==='observed'?'Наблюдение изображения':'Со слов клиента'}{f.conflict?' · есть противоречие':''}</p><p className="muted">Источник: <a href={`#message-${f.source.message_id}`}>сообщение клиента</a> · {f.source.quote||'текущий анализ изображения'}</p><button disabled={view.busy||!!intent.current||!(edits[f.field]??f.value).trim()} onClick={()=>void save(f)}>Подтвердить поле {labels[f.field]}</button></article>)}{data.missing.length>0&&<p>Неизвестно: {data.missing.map(f=>labels[f]).join(', ')}</p>}<button className="secondary" disabled={compared&&comparisons.busy} onClick={()=>void compare()}>Сравнить с примерами мастера</button>{compared&&<div aria-label="Сравнение примеров мастера"><p>Время прошлых работ видно только мастеру. Это не оценка нового запроса.</p>{comparisons.error&&<p role="alert">{comparisons.error}</p>}{!comparisons.busy&&!comparisons.error&&comparisons.items.length===0&&<p>Подтверждённых текущих примеров нет.</p>}{comparisons.items.map(m=><article key={m.case.case_id}><h4>{m.case.data.description}</h4><p>Совпадает: {m.matches.map(f=>labels[f]??f).join(', ')||'нет'} · различается: {m.differences.map(f=>labels[f]??f).join(', ')||'нет'} · неизвестно: {m.unknown.map(f=>labels[f]??f).join(', ')||'нет'}</p><p>Источник: подтверждённый пример, версия {m.case.version}. Рабочее время: {m.case.data.working_minutes??'неизвестно'}, занятое: {m.case.data.occupied_minutes??'неизвестно'} мин.</p></article>)}</div>}</>}{scope.conversation&&
  <RequestDraftPanel key={draftScopeKey} scope={scope} data={data} csrf={session.csrf_token} expired={expired}/>
 }</section>;
}

type DraftChoice={fingerprint:string;messageId:string;fields:FieldId[];confirmed:boolean};
type DraftAttempt={body:DraftCommand;key:string;requestId?:string};

function draftError(error:IntakeError):string{
 switch(error.code){
  case 'NEEDS_CLARIFICATION':return 'Уточните, к какой работе относятся выбранное начало и сведения.';
  case 'STALE_STATE':return 'Сведения изменились. Обновите сводку и заново выберите сведения для заявки.';
  case 'IDEMPOTENCY_KEY_CONFLICT':return 'Команда с этим ключом уже сохранена с другими сведениями. Обновите сводку.';
  default:return 'Команда для этой заявки недоступна.';
 }
}

function factStatus(fact:Fact){
 if(fact.status==='owner-confirmed')return 'Подтверждено мастером';
 return fact.status==='observed'?'Наблюдение изображения':'Со слов клиента';
}

function DraftCard({draft}:{draft:ServiceRequestDraft}){
 return <section aria-label="Черновик заявки">
  <h4>Черновик заявки</h4>
  <article>
   <dl>
    <dt>ID заявки</dt><dd><code data-testid="service-request-id">{draft.request_id}</code></dd>
    <dt>Услуга</dt><dd>{draft.service_name}</dd>
    <dt>Ревизия</dt><dd>{draft.revision}</dd>
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
 </section>;
}

function RequestDraftPanel({scope,data,csrf,expired}:{scope:IntakeScope;data:Intake|null;csrf:string;expired:()=>void}){
 const sourceId=useId();
 const [draft,setDraft]=useState<ServiceRequestDraft|null>(null);
 const [choice,setChoice]=useState<DraftChoice|null>(null);
 const [busy,setBusy]=useState(true);
 const [readable,setReadable]=useState(false);
 const [error,setError]=useState('');
 const active=useRef<AbortController|null>(null);
 const pending=useRef<DraftAttempt|null>(null);

 async function open(attempt:DraftAttempt|null){
  if(active.current)return;
  const controller=new AbortController();
  active.current=controller;
  const signal=controller.signal;
  setBusy(true);
  setError('');
  try{
   if(attempt&&!attempt.requestId){
    const receipt=await intakeApi.saveDraft(scope,attempt.body,attempt.key,csrf,signal);
    if(signal.aborted)return;
    attempt.requestId=receipt.request_id;
   }
   const result=await intakeApi.draft(scope,attempt?.requestId,signal);
   if(signal.aborted)return;
   setDraft(result);
   setReadable(true);
   pending.current=null;
  }catch(failure){
   if(signal.aborted)return;
   if(failure instanceof IntakeError&&[400,401,403,404,409,422].includes(failure.status)){
    pending.current=null;
    setChoice(null);
    setError(draftError(failure));
    if([401,403,404].includes(failure.status)){setDraft(null);setReadable(false);}
    if(failure.status===401)expired();
   }else if(attempt){
    setError(attempt.requestId?'Заявка сохранена. Карточку можно открыть повторно.':'Результат создания неизвестен. Можно повторить ту же команду.');
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
  void open(null);
  return()=>{active.current?.abort();active.current=null;pending.current=null;};
 },[]);

 const canChoose=data?.template_revision==='tattoo_intake_v1'&&!!data.service_id
  &&data.category!=='AMBIGUOUS'&&data.category!=='FAQ_ONLY';
 const selected=choice?.fingerprint===data?.fingerprint?choice:null;
 const sourceIndex=data?.sources.findIndex(source=>source.message_id===selected?.messageId)??-1;
 const source=sourceIndex<0?undefined:data?.sources[sourceIndex];
 const eligible=source&&data?data.facts.filter(fact=>data.sources.findIndex(item=>
  item.message_id===fact.source.message_id&&item.source_version===fact.source.source_version)>=sourceIndex):[];
 const waiting=pending.current;
 const locked=busy||!!waiting;

 function start(){
  if(!data||!source||!selected?.confirmed||locked||!canChoose||pending.current)return;
  const attempt:DraftAttempt={key:crypto.randomUUID(),body:{
   expected_version:data.version,
   expected_fingerprint:data.fingerprint,
   intent_source:{message_id:source.message_id,source_version:source.source_version},
   fields:eligible.filter(fact=>selected.fields.includes(fact.field)).map(fact=>fact.field),
   selection:'ONE_WORK',
  }};
  pending.current=attempt;
  void open(attempt);
 }

 return <>
  {draft&&<DraftCard draft={draft}/>}
  {error&&<p role="alert">{error}</p>}
  {waiting&&!busy&&<button type="button" onClick={()=>void open(waiting)}>
   {waiting.requestId?'Открыть сохранённую заявку':'Повторить создание заявки'}
  </button>}
  {!readable&&!busy&&<button type="button" onClick={()=>void open(null)}>Обновить заявку</button>}
  {readable&&canChoose&&data&&<fieldset aria-label="Выбор сведений для заявки" disabled={locked} style={{minWidth:0}}>
   <label htmlFor={sourceId}>Начало работы</label>
   <select id={sourceId} value={source?.message_id??''} style={{maxWidth:'100%'}} onChange={event=>setChoice({
    fingerprint:data.fingerprint,messageId:event.target.value,fields:[],confirmed:false,
   })}>
    <option value="">Выберите исходное сообщение</option>
    {data.sources.map(item=><option key={item.message_id} value={item.message_id}>
     {Array.from(item.text.trim()).slice(0,100).join('')||'Входящее фото'} · #{item.message_id.slice(-6)}
    </option>)}
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
   <button type="button" onClick={start} disabled={!source||!selected?.confirmed}>Создать или открыть заявку</button>
  </fieldset>}
 </>;
}
