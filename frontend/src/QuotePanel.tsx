import {useEffect,useState} from 'react';
import type {ApprovalSelection} from './escalation-api';
import {IntakeError,intakeApi} from './intake-api';
import type {IntakeScope,QuoteDelivery,QuoteStatus,ServiceRequestDraft} from './intake-api';

const statusText:Record<QuoteStatus,string>={
 PREPARED:'Предложение подготовлено',
 QUEUED:'Предложение в очереди на отправку',
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

export function QuotePanel({scope,draft,refresh,approvalChange,expired}:Props){
 const [delivery,setDelivery]=useState<QuoteDelivery|null>(null);
 const [error,setError]=useState(false);

 useEffect(()=>{
  const controller=new AbortController(),{signal}=controller;
  let timer:ReturnType<typeof setTimeout>|undefined;
  let refreshes=0;
  setDelivery(null);setError(false);

  async function load(){
   try{
    const result=await intakeApi.quote(scope,draft.request_id,signal);
    if(signal.aborted)return;
    setDelivery(result);
    if(result.status==='QUEUED'&&refreshes++<8)timer=setTimeout(()=>void load(),2000);
   }catch(cause){
    if(signal.aborted)return;
    setDelivery(null);setError(true);
    if(cause instanceof IntakeError&&cause.status===401)expired();
   }
  }

  void load();
  return ()=>{controller.abort();clearTimeout(timer);};
 },[draft,refresh,approvalChange]);

 const quote=delivery?.quote;
 const material=quote?.material;
 const reason=delivery?.reason;
 return <section aria-label="Предложение клиенту" style={{overflowWrap:'anywhere'}}>
  <h4>Предложение клиенту</h4>
  {error&&<p role="alert">Не удалось обновить статус предложения.</p>}
  {!error&&!delivery&&<p role="status">Проверяем статус предложения…</p>}
  {delivery&&<>
   <p role="status">{delivery.status?statusText[delivery.status]:reason?'Предложение ещё не подготовлено':'Предложения пока нет'}</p>
   {reason&&<p>{reasonText[reason]??<>Причина <code>{reason}</code></>}</p>}
  </>}
  {quote&&material&&<article aria-label="Условия предложения">
   <p><strong>{quote.code}</strong> · версия {quote.version}{material.request_revision!==draft.revision&&` · для ревизии заявки ${material.request_revision}`}</p>
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
  </article>}
 </section>;
}
