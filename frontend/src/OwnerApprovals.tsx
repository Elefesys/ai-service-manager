import {useEffect,useId,useRef,useState} from 'react';
import type {Session} from './api';
import {priceAmount} from './configuration-api';
import {approvalApi,draftApprovalSelection,EscalationError} from './escalation-api';
import type {ApprovalBody,ApprovalCard,ApprovalSelection,ApprovalSource,SourceBinding} from './escalation-api';
import {IntakeError,intakeApi,labels} from './intake-api';

const statusText:Record<ApprovalCard['status'],string>={
  PENDING:'Ожидает решения мастера',APPROVED:'Условия подтверждены',CLARIFICATION:'Запрошено уточнение',
  DECLINED:'Мастер отказал',EXPIRED:'Срок истёк',STALE:'Условия изменились',REVOKED:'Запрос отозван',
};
const failure=(error:unknown)=>{
  const code=error instanceof EscalationError||error instanceof IntakeError?error.code:'';
  if(code==='APPROVAL_EXPIRED')return statusText.EXPIRED;
  if(code==='APPROVAL_REVOKED')return statusText.REVOKED;
  if(code==='STALE_STATE')return statusText.STALE;
  if(code==='IDEMPOTENCY_KEY_CONFLICT')return 'По запросу уже сохранено другое решение.';
  if(code==='NEEDS_CLARIFICATION')return 'Сначала уточните сведения о работе.';
  return 'Не удалось получить актуальное решение.';
};
const factStatus={'client-stated':'Со слов клиента','owner-confirmed':'Подтверждено мастером','observed':'Указано в источнике'};
const shortId=(card:ApprovalCard)=>card.request_id.slice(-6);
const primaryFact=(card:ApprovalCard)=>card.basis.facts.find(item=>item.field==='idea')?.value;
const depositText=(deposit:ApprovalCard['basis']['deposit'])=>{
  if(deposit.mode==='NONE')return 'Без предоплаты';
  if(deposit.mode==='FULL_PREPAYMENT')return 'Полная предоплата';
  if(deposit.amount_minor!==null)return priceAmount(deposit.amount_minor);
  if(deposit.percent!==null)return deposit.percent+'%';
  return 'Условия определяет мастер';
};

function shownPrice({amount_minor,price_range}:ApprovalCard['basis']|NonNullable<NonNullable<ApprovalCard['decision']>['terms']>){
  if(price_range)return priceAmount(price_range.lower_minor)+' – '+priceAmount(price_range.upper_minor)+' · предварительный диапазон';
  return amount_minor===null?'Определяет мастер':priceAmount(amount_minor);
}

type SourcePreviewState =
  | {state:'loading'}
  | {state:'unavailable'|'changed'|'failed'}
  | {state:'ready';source:ApprovalSource};

type PanelProps={
  session:Session;workspace:string;selected:ApprovalSelection|null;
  related:(ids:readonly string[])=>void;expired:()=>void;recover:()=>void;denied:()=>void;
  changed?:(selection:ApprovalSelection)=>void;
};
type Attempt=Readonly<{scope:ApprovalSelection;body:ApprovalBody}>;

export function OwnerApprovals({session,workspace,selected,related,expired,recover,denied,changed}:PanelProps){
  const [cards,setCards]=useState<ApprovalCard[]>([]);
  const [cursor,setCursor]=useState<string|null>(null);
  const [selection,setSelection]=useState<ApprovalSelection|null>(null);
  const [detail,setDetail]=useState<ApprovalCard|null>(null);
  const [listBusy,setListBusy]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [listError,setListError]=useState('');
  const [retry,setRetry]=useState(false);
  const listRead=useRef<AbortController|null>(null), detailRead=useRef<AbortController|null>(null);
  const command=useRef<AbortController|null>(null), attempt=useRef<Attempt|null>(null);
  const region=useRef<HTMLElement|null>(null);

  function sessionFailure(cause:unknown){
    if(!(cause instanceof EscalationError||cause instanceof IntakeError))return;
    if(cause.status===401)expired();
    if(cause.status===403&&cause.code==='CSRF_REJECTED')recover();
    else if(cause.status===403)denied();
  }
  async function list(before:string|null=null){
    listRead.current?.abort();
    const controller=new AbortController(),{signal}=controller;
    listRead.current=controller;
    setListBusy(true);setListError('');related([]);
    try{
      const page=await approvalApi.list(workspace,before,signal);
      if(signal.aborted)return;
      setCards(old=>before?[...old.filter(item=>!page.items.some(fresh=>fresh.approval_id===item.approval_id)),...page.items]:page.items);
      setCursor(page.next);
    }catch(cause){
      if(!signal.aborted){setCards([]);setCursor(null);setListError(failure(cause));sessionFailure(cause);}
    }finally{if(!signal.aborted){setListBusy(false);listRead.current=null;}}
  }
  function update(card:ApprovalCard){
    setDetail(card);
    setCards(old=>old.some(item=>item.approval_id===card.approval_id)
      ?old.map(item=>item.approval_id===card.approval_id?card:item)
      :[card,...old.filter(item=>item.request_id!==card.request_id)]);
  }
  async function read(scope:ApprovalSelection){
    if(command.current||attempt.current)return;
    detailRead.current?.abort();
    const controller=new AbortController(),{signal}=controller;
    detailRead.current=controller;
    setSelection(scope);setDetail(null);setBusy(true);setError('');
    try{
      const card=await approvalApi.read(scope,signal);
      if(!signal.aborted)update(card);
    }catch(cause){
      if(!signal.aborted){setError(failure(cause));sessionFailure(cause);}
    }finally{if(!signal.aborted){setBusy(false);detailRead.current=null;}}
  }

  useEffect(()=>{
    void list();
    return ()=>{listRead.current?.abort();detailRead.current?.abort();command.current?.abort();related([]);};
  },[session,workspace]);
  useEffect(()=>{
    related(listBusy?[]:cards.flatMap(card=>card.related_escalation_id?[card.related_escalation_id]:[]));
  },[cards,listBusy,related]);
  useEffect(()=>{
    if(selected?.workspace===workspace){
      void read(selected);
      void list();
      region.current?.focus({preventScroll:true});
      region.current?.scrollIntoView?.({block:'start'});
    }
  },[selected,workspace]);

  async function send(next:Attempt){
    if(command.current||detailRead.current)return;
    const controller=new AbortController(),{signal}=controller;
    command.current=controller;attempt.current=next;
    setBusy(true);setRetry(false);setError('');
    let reread=false;
    try{
      const result=await approvalApi.decide(next.scope,next.body,session.csrf_token,signal);
      if(signal.aborted)return;
      attempt.current=null;
      update(result);
      changed?.(draftApprovalSelection(result));
    }catch(cause){
      if(signal.aborted)return;
      if(cause instanceof EscalationError&&[404,409,422].includes(cause.status)){
        attempt.current=null;reread=true;
      }else{
        setRetry(true);
        setError('Результат пока неизвестен. Можно повторить то же решение.');
      }
      sessionFailure(cause);
    }finally{
      if(!signal.aborted){command.current=null;setBusy(false);}
    }
    if(reread){await read(next.scope);setError('Подтверждение отклонено. Карточка обновлена.');}
  }

  async function reopen(card:ApprovalCard){
    if(command.current||attempt.current||detailRead.current)return;
    const controller=new AbortController(),{signal}=controller;
    command.current=controller;
    setBusy(true);setError('');
    try{
      const scope=approvalApi.scope({
        workspace:card.workspace_id,business:card.business_id,conversation:card.conversation_id,client:card.client_id,
      },card.request_id);
      const draft=await intakeApi.draft(scope,scope.request,signal);
      if(!draft||signal.aborted)return;
      const current=await approvalApi.open(scope,draft.revision,session.csrf_token,signal);
      if(signal.aborted)return;
      if(current){setSelection(draftApprovalSelection(current));update(current);}
      else setError('Цена и длительность уже утверждены.');
      void list();
    }catch(cause){
      if(!signal.aborted){setError(failure(cause));sessionFailure(cause);}
    }finally{if(!signal.aborted){command.current=null;setBusy(false);}}
  }

  return <section ref={region} tabIndex={-1} aria-label="Решения по заявкам" className="escalation-detail" style={{overflowWrap:'anywhere'}}>
    <div className="billing-heading">
      <h3>Решения по заявкам</h3>
      <button type="button" className="secondary" disabled={listBusy||busy||retry} onClick={()=>{void list();if(selection)void read(selection);}}>
        Обновить решения по заявкам
      </button>
    </div>
    {listBusy&&<p role="status">Читаем заявки…</p>}
    {listError&&<p role="alert">{listError}</p>}
    <ul className="escalation-list">{cards.map(card=><li key={card.approval_id}>
      <button type="button" className="secondary" data-testid={'approval-'+card.approval_id}
        aria-pressed={selection?.approval===card.approval_id} disabled={busy||retry} onClick={()=>void read(draftApprovalSelection(card))}>
        <strong>{primaryFact(card)||card.basis.service_name} · #{shortId(card)}</strong>
        <span>{card.basis.service_name} · {statusText[card.status]}</span>
      </button>
    </li>)}</ul>
    {cursor&&<button type="button" className="secondary" disabled={busy||retry||listBusy} onClick={()=>void list(cursor)}>Ещё решения по заявкам</button>}
    {error&&<p role="alert">{error}</p>}
    {retry&&attempt.current&&<button type="button" disabled={busy} onClick={()=>{const retry=attempt.current;if(retry)void send(retry);}}>Повторить то же решение</button>}
    {detail&&<SelectedApproval key={detail.approval_id+detail.version} card={detail} locked={busy||retry}
      submit={body=>void send({scope:draftApprovalSelection(detail),body})} reopen={()=>void reopen(detail)} onAccessError={sessionFailure}/>}
  </section>;
}

function SelectedApproval({card,locked,submit,reopen,onAccessError}:{
  card:ApprovalCard;locked:boolean;submit:(body:ApprovalBody)=>void;reopen:()=>void;onAccessError:(cause:unknown)=>void;
}){
  const {basis,decision}=card;
  const [price,setPrice]=useState(''), [minutes,setMinutes]=useState(''), [note,setNote]=useState('');
  const [error,setError]=useState('');
  const id=useId();
  const inactive=['EXPIRED','STALE','REVOKED'].includes(card.status);
  const knownPrice=basis.amount_minor!==null||basis.price_range!==null,knownDuration=basis.occupied_minutes!==null;
  const [preview,setPreview]=useState<SourcePreviewState|null>(null);
  const previewRead=useRef<AbortController|null>(null);
  const previewRegion=useRef<HTMLElement|null>(null);
  useEffect(()=>()=>previewRead.current?.abort(),[]);
  useEffect(()=>{if(preview?.state==='loading')previewRegion.current?.focus();},[preview]);

  async function showSource(source:SourceBinding){
    previewRead.current?.abort();
    const controller=new AbortController();
    previewRead.current=controller;
    setPreview({state:'loading'});
    try{
      const reply=await approvalApi.source(draftApprovalSelection(card),source,controller.signal);
      if(!controller.signal.aborted)setPreview({state:'ready',source:reply});
    }catch(cause){
      if(controller.signal.aborted)return;
      const status=cause instanceof EscalationError?cause.status:null;
      setPreview({state:status===409?'changed':status===404?'unavailable':'failed'});
      onAccessError(cause);
    }finally{
      if(previewRead.current===controller)previewRead.current=null;
    }
  }
  function sourceLink(source:SourceBinding,label:string){
    return <a href={'#'+id+'-source'} onClick={event=>{event.preventDefault();void showSource(source);}}>{label}</a>;
  }
  function decide(operation:ApprovalBody['operation']){
    const value=note.trim()?note:undefined;
    let amount_minor:number|undefined,occupied_minutes:number|undefined;
    if(operation==='APPROVE'){
      const match=/^([0-9]{1,10})(?:[.,]([0-9]{1,2}))?$/.exec(price.trim());
      if(!knownPrice){
        amount_minor=match?Number(match[1])*100+Number((match[2]??'').padEnd(2,'0')):0;
        if(amount_minor<1||amount_minor>100_000_000_000){setError('Укажите цену в рублях с точностью до копейки.');return;}
      }
      if(!knownDuration){
        occupied_minutes=/^[0-9]{1,5}$/.test(minutes)?Number(minutes):0;
        if(occupied_minutes<1||occupied_minutes>10080){setError('Укажите от 1 до 10 080 минут.');return;}
      }
    }
    if(operation==='CLARIFY'&&!value){setError('Напишите, что нужно уточнить.');return;}
    setError('');
    submit(Object.freeze({expected_version:card.version,action:card.action,operation,amount_minor,occupied_minutes,
      note:operation==='WITHDRAW'?undefined:value}));
  }
  return <article aria-label="Карточка решения по заявке" data-testid={'approval-detail-'+card.approval_id} className="detail">
    <h4>{basis.service_name} · заявка #{shortId(card)}</h4>
    <p role="status">{statusText[card.status]}</p>
    <p>Ревизия {card.request_revision} · срок {new Date(card.expires_at).toLocaleString('ru-RU')}</p>
    {basis.question&&<p>{basis.question}</p>}
    <ul aria-label={inactive?'Сведения на момент запроса':'Проверенные сведения'}>
      {basis.facts.map(fact=><li key={fact.field}>{labels[fact.field]} · {fact.value} · {factStatus[fact.status]} ·  {sourceLink(fact.source,'Источник')}</li>)}
    </ul>
    <p>{sourceLink(basis.intent_source,'Исходная реплика заявки')}</p>
    {basis.complex_work&&<p>{basis.complex_work.category==='COVER_UP'?'Перекрытие':'Сложная работа'} · {sourceLink(basis.complex_work.source,'Уточнение клиента')}</p>}
    {preview&&<section id={id+'-source'} ref={previewRegion} tabIndex={-1} aria-label="Реплика заявки">
      <h5>Реплика заявки</h5>
      {preview.state==='loading'&&<p role="status">Загружаем реплику…</p>}
      {preview.state==='changed'&&<p role="alert">Версия реплики изменилась.</p>}
      {preview.state==='unavailable'&&<p role="alert">Реплика недоступна.</p>}
      {preview.state==='failed'&&<p role="alert">Не удалось прочитать реплику.</p>}
      {preview.state==='ready'&&<p className="exact-answer" data-testid={'approval-source-'+preview.source.message_id}>
        {preview.source.text??'Фото без подписи'}
      </p>}
    </section>}
    {basis.unavailable_fields.length>0&&<p>Нужны актуальные сведения по полям {basis.unavailable_fields.map(field=>labels[field]).join(', ')}.</p>}
    {(!decision?.terms||inactive)&&<dl>
      <dt>Цена на момент запроса</dt><dd>{shownPrice(basis)}</dd>
      <dt>Длительность следующего сеанса на момент запроса</dt><dd>{basis.occupied_minutes===null?'Определяет мастер':basis.occupied_minutes+' мин'}</dd>
      <dt>Предоплата</dt><dd>{depositText(basis.deposit)}</dd>
    </dl>}
    {decision&&<>
      {decision.terms&&<section aria-label={inactive?'Прежние условия':'Подтверждённые условия'}>
        <h5>{inactive?'Прежние условия':'Подтверждённые условия'}</h5>
        <dl>
          <dt>Цена</dt><dd>{shownPrice(decision.terms)}{!decision.terms.price_range&&' · '+(knownPrice?'Расчёт по правилу услуги':'Утверждено мастером')}</dd>
          <dt>Длительность следующего сеанса</dt><dd>{decision.terms.occupied_minutes} мин · {knownDuration?'Оценка по правилу услуги':'Утверждено мастером'}</dd>
          <dt>Предоплата</dt><dd>{depositText(basis.deposit)}</dd>
        </dl>
      </section>}
      {decision.submitted.note&&<p className="exact-answer">{decision.submitted.note}</p>}
      <p>Решение <code>{decision.decision_id}</code></p>
    </>}
    <details>
      <summary>Основания и исполнитель</summary>
      <dl>
        <dt>Выпуск настроек услуги</dt><dd>{basis.release_id} · версия {basis.activation_version}</dd>
        <dt>Расчёт цены</dt><dd>{basis.price_calculation_id}</dd>
        <dt>Оценка длительности</dt><dd>{basis.assessment_id}</dd>
        <dt>Ответственный мастер</dt><dd>{card.assignee_user_account_id}</dd>
        {decision&&<><dt>Сохранил</dt><dd>{decision.actor_user_account_id} · {decision.decided_at}</dd></>}
      </dl>
    </details>
    {card.can_resolve&&<form onSubmit={event=>{event.preventDefault();if(basis.can_approve)decide('APPROVE');}}>
      <fieldset disabled={locked} style={{minWidth:0}}>
        <legend>Решение мастера</legend>
        {basis.can_approve&&<p>Цена, длительность и предоплата войдут в условия для клиента.</p>}
        {basis.can_approve&&!knownPrice&&<>
          <label htmlFor={id+'-price'}>Цена, ₽</label>
          <input id={id+'-price'} inputMode="decimal" maxLength={14} value={price} onChange={event=>setPrice(event.target.value)}/>
        </>}
        {basis.can_approve&&!knownDuration&&<>
          <label htmlFor={id+'-duration'}>Длительность следующего сеанса, мин</label>
          <input id={id+'-duration'} inputMode="numeric" maxLength={5} value={minutes} onChange={event=>setMinutes(event.target.value)}/>
        </>}
        <label htmlFor={id+'-note'}>Пояснение или вопрос</label>
        <textarea id={id+'-note'} maxLength={300} rows={2} value={note} onChange={event=>setNote(event.target.value)}/>
        {error&&<p role="alert">{error}</p>}
        <div className="control-actions">
          {basis.can_approve&&<button type="submit">Подтвердить условия</button>}
          <button type="button" className="secondary" onClick={()=>decide('CLARIFY')}>Запросить уточнение</button>
          <button type="button" className="secondary" onClick={()=>decide('DECLINE')}>Отказать по заявке</button>
        </div>
      </fieldset>
    </form>}
    {inactive&&<button type="button" disabled={locked} onClick={reopen}>Открыть новый запрос</button>}
    {card.authorization_current&&<button type="button" className="secondary" disabled={locked} onClick={()=>decide('WITHDRAW')}>Отозвать подтверждение</button>}
  </article>;
}
