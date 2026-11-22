import {useEffect,useRef,useState} from 'react';
import type {ApprovalSelection} from './escalation-api';
import {IntakeError,intakeApi} from './intake-api';
import type {IntakeScope,QuoteAgreement,QuoteDelivery,QuoteReplyNotice,QuoteStatus,RequestQuote,ServiceRequestDraft} from './intake-api';

const statusText:Record<QuoteStatus,string>={
 PREPARED:'Предложение подготовлено',
 QUEUED:'Предложение в очереди на отправку',
 DISPATCHING:'Отправка началась, ожидаем подтверждения',
 HELD:'Отправка удержана',
 SENT:'Предложение отправлено клиенту',
 UNKNOWN:'UNKNOWN · Доставка не подтверждена',
 FAILED:'Ошибка отправки предложения',
 NEEDS_CLARIFICATION:'Нужно уточнение',
};

const reasonText:Record<string,string>={
 AWAITING_TERMS:'Нужны цена и длительность следующего сеанса.',
 EXACT_PRICE_REQUIRED:'Уточните точную цену. Она нужна для расчёта процентной или полной предоплаты.',
 DEPOSIT_TERMS_UNCLEAR:'Уточните условия предоплаты.',
 APPROVAL_CLARIFICATION:'Мастер запросил уточнение условий.',
 APPROVAL_DECLINED:'Мастер отказал по заявке.',
 EXPIRED:'Срок действия условий истёк.',
 STALE:'Условия заявки изменились.',
 REVOKED:'Решение или полномочия мастера больше не действуют.',
 HUMAN_CONTROL:'Управление диалогом у мастера.',
 CONTROL_CHANGED:'Режим управления диалогом изменился.',
 ACTIVATION_REQUIRED:'Автоматику для диалога нужно разрешить.',
 CONTEXT_CONFIRMATION_REQUIRED:'Нужно подтвердить актуальный контекст диалога.',
 CONTEXT_POLICY_PAUSED:'Автоматика приостановлена оператором.',
 CONTEXT_INPUT_PENDING:'Входящие сообщения ещё обрабатываются.',
 CONTEXT_INPUT_UNRESOLVED:'Входящие сообщения требуют проверки.',
 CONTEXT_UNRESOLVED:'В контексте остались нерешённые вопросы.',
 CONTEXT_COVERAGE_REQUIRED:'Для проверки контекста нужна дополнительная история.',
 NEW_OBSERVATION:'Канал сообщил об изменениях после сверки.',
 CHANNEL_UNAVAILABLE:'Канал для отправки недоступен.',
 CHANNEL_RIGHTS_UNAVAILABLE:'У канала нет подтверждённого права на отправку.',
 CHANNEL_WINDOW_CLOSED:'Окно ответа в канале закрыто.',
 UNKNOWN_EXTERNAL_RESULT:'Сообщение могло быть доставлено. Автоматический повтор отключён.',
};

type Props={
 scope:IntakeScope;draft:ServiceRequestDraft;refresh:string;
 approvalChange:ApprovalSelection|null;expired:()=>void;
};

function DeliveryStatus({status,reason}:Pick<QuoteDelivery,'status'|'reason'>){
 return <>
  <p role="status">{status?statusText[status]:reason?'Предложение ещё не подготовлено':'Предложения пока нет'}</p>
  {reason&&<p>{reasonText[reason]??<>Причина <code>{reason}</code></>}</p>}
 </>;
}

function QuoteTerms({quote,revision}:{quote:RequestQuote;revision:string}){
 const material=quote.material;
 return <article aria-label="Условия предложения">
  <p><strong>{quote.code}</strong> · версия {quote.version}{material.request_revision!==revision&&` · для ревизии заявки ${material.request_revision}`}</p>
  <p className="message-text" data-testid="quote-text">{quote.text}</p>
  <details>
   <summary>Источники условий</summary>
   <dl className="billing-facts">
    <dt>{material.price_reference_id===material.decision_id?'Цена мастера':'Расчёт цены'}</dt><dd><code>{material.price_reference_id}</code></dd>
    <dt>{material.duration_reference_id===material.decision_id?'Длительность от мастера':'Оценка длительности'}</dt><dd><code>{material.duration_reference_id}</code></dd>
    <dt>ID предложения</dt><dd><code>{quote.quote_id}</code></dd>
    <dt>Отпечаток условий</dt><dd><code>{quote.terms_sha256}</code></dd>
   </dl>
  </details>
 </article>;
}

const replyText:Record<QuoteReplyNotice['outcome'],string>={
 NEEDS_CLARIFICATION:'Клиент ответил «да». Уточните, какое предложение он принимает, и попросите прислать его код.',
 DELIVERY_UNCONFIRMED:'Сверьте доставку и попросите клиента прислать новое согласие.',
 HUMAN_CONTROL:'Ответ поступил при управлении мастером. Для заказа нужно новое согласие клиента.',
 CONTROL_CHANGED:'Режим управления изменился. Для заказа нужно новое согласие клиента.',
 EXPIRED:'Срок предложения истёк. Для заказа нужно действующее предложение и новое согласие.',
 REVOKED:'Основание предложения отозвано. Для заказа нужно новое предложение.',
 STALE:'Код относится к прежним условиям. Для заказа нужно согласие на действующие условия.',
 REVIEW_REQUIRED:'Ответ клиента требует проверки мастером.',
 DECLINED:'Клиент отклонил предложение.',
};

function Agreement({agreement,revision}:{agreement:QuoteAgreement;revision:string}){
 const {source,quote}=agreement;
 const evidence=useRef<HTMLDetailsElement>(null);
 return <section aria-label="Согласованный заказ" data-testid="quote-agreement">
  <h5>Согласованный заказ</h5>
  <dl className="billing-facts">
   <dt>Заказ</dt><dd><code data-testid="service-order-id">{agreement.order_id}</code></dd>
   <dt>Согласие клиента</dt><dd><code data-testid="quote-acceptance-id">{agreement.acceptance_id}</code></dd>
   <dt>Следующий сеанс</dt><dd>Запланирован без даты · {quote.material.occupied_minutes} мин <code data-testid="service-session-id">{agreement.session_id}</code></dd>
  </dl>
  <p><a href={`#consent-${source.message_id}`} onClick={event=>{
   event.preventDefault();
   if(evidence.current){evidence.current.open=true;evidence.current.focus();}
  }}>Первая подтверждающая реплика</a></p>
  <details id={`consent-${source.message_id}`} ref={evidence} tabIndex={-1}>
   <summary>Согласие на {quote.code}</summary>
   <p className="message-text">{source.status==='AVAILABLE'?source.text:
    source.status==='CHANGED'?'Версия подтверждающей реплики изменилась.':'Подтверждающая реплика недоступна.'}</p>
  </details>
  <details>
   <summary>Принятые условия · {quote.code}</summary>
   <QuoteTerms quote={quote} revision={revision}/>
  </details>
 </section>;
}

export function QuotePanel({scope,draft,refresh,approvalChange,expired}:Props){
 const [delivery,setDelivery]=useState<QuoteDelivery|null>(null);
 const [error,setError]=useState(false);

 useEffect(()=>{
  const controller=new AbortController(),{signal}=controller;
  let timer:ReturnType<typeof setTimeout>|undefined;
  let queuedRefreshes=0;
  setDelivery(null);setError(false);

  async function load(){
   try{
    const result=await intakeApi.quote(scope,draft.request_id,signal);
    if(signal.aborted)return;
    setDelivery(result);
    const status=result.previous?.status??result.status;
    // Recovery of an in-flight attempt can outlast the queue polling window.
    if(status==='DISPATCHING')queuedRefreshes=0;
    else if(status!=='QUEUED'||queuedRefreshes++>=8)return;
    timer=setTimeout(()=>void load(),2000);
   }catch(cause){
    if(signal.aborted)return;
    setDelivery(null);setError(true);
    if(cause instanceof IntakeError&&cause.status===401)expired();
   }
  }

  void load();
  return ()=>{controller.abort();clearTimeout(timer);};
 },[draft,refresh,approvalChange]);

 const previous=delivery?.previous;
 return <section aria-label="Предложение клиенту" style={{overflowWrap:'anywhere'}}>
  <h4>Предложение клиенту</h4>
  {error&&<p role="alert">Не удалось обновить статус предложения.</p>}
  {!error&&!delivery&&<p role="status">Проверяем статус предложения…</p>}
  {delivery&&<DeliveryStatus status={delivery.status} reason={delivery.reason}/>}
  {delivery?.quote&&<QuoteTerms quote={delivery.quote} revision={draft.revision}/>}
  {delivery?.agreement&&<Agreement key={delivery.agreement.acceptance_id} agreement={delivery.agreement} revision={draft.revision}/>}
  {delivery?.reply_notice&&<p role="status">{replyText[delivery.reply_notice.outcome]}{' '}
   <a href={`#message-${delivery.reply_notice.message_id}`}>Ответ клиента</a></p>}
  {previous&&<section aria-label="Предыдущая версия">
   <h5>Предыдущая версия</h5>
   <DeliveryStatus status={previous.status} reason={previous.reason}/>
   <QuoteTerms quote={previous.quote} revision={draft.revision}/>
  </section>}
 </section>;
}
