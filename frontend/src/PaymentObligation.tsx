import {useEffect, useRef, useState} from 'react';
import {clientPaymentsApi} from './client-payments-api';
import type {Checkout, HoldPayment} from './client-payments-api';
import {IntakeError} from './intake-api';
import type {Booking, SchedulingScope} from './scheduling-api';
import {deadlineText} from './scheduling-api';

type Props = {
  scope: SchedulingScope;
  booking: Extract<Booking, {expires_at: string}>;
  expired: () => void;
  csrf: string;
};
type State = HoldPayment | {error: string; retry?: boolean};

function money(minor: number) {
  const rubles = Math.floor(minor / 100).toLocaleString('ru-RU');
  const kopecks = minor % 100;
  return kopecks ? `${rubles},${String(kopecks).padStart(2, '0')}` : rubles;
}

function checkoutMessage(attempt: Checkout) {
  if (attempt.delivery === 'SENT') return 'Ссылка на предоплату отправлена клиенту.';
  if (attempt.delivery === 'UNKNOWN') return 'Доставка ссылки не подтверждена.';
  switch (attempt.reason) {
    case 'CARD_MINIMUM': return 'Для оплаты банковской картой нужна сумма от 1 ₽.';
    case 'STORE_UNAVAILABLE': return 'Тестовый магазин недоступен.';
    case 'HOLD_INACTIVE': return 'Удержание больше не действует. Ссылка не отправлена.';
    case 'CONTEXT_CHANGED': return 'Диалог изменился. Ссылка не отправлена.';
    case 'CHANNEL_RIGHTS_UNAVAILABLE': return 'У канала нет права отправить ссылку.';
    case 'IDEMPOTENCE_EXPIRED':
    case 'PROVIDER_UNKNOWN': return 'Результат создания оплаты не подтверждён.';
  }
  if (attempt.status === 'CANCELED') return 'ЮKassa отменила оплату.';
  if (attempt.status === 'NO_LINK') return 'Платёж у ЮKassa без доступной ссылки.';
  if (attempt.delivery === 'FAILED') return 'Ссылка на предоплату не отправлена.';
  return 'Готовим ссылку на предоплату.';
}

export function PaymentObligation({
  scope: {workspace, business, conversation, client, request, quote, order, session},
  booking: {hold_id, allocation_id, outcome, expires_at}, expired, csrf,
}: Props) {
  const [state, setState] = useState<State | null>(null);
  const [retry, setRetry] = useState(0);
  const key = useRef<string>(null);
  const [attempt, setAttempt] = useState<Checkout | null>(null);
  const [checkoutError, setCheckoutError] = useState('');
  const [replacing, setReplacing] = useState(false);
  const replaceKey = useRef<{attempt: string; key: string} | null>(null);
  const checkoutScope = useRef<AbortController | null>(null);
  const onExpired = useRef(expired);
  onExpired.current = expired;

  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    const scope = {workspace, business, conversation, client, request, quote, order, session};
    const hold = {hold_id, allocation_id};
    async function load() {
      try {
        let view = await clientPaymentsApi.read(scope, hold, signal);
        if (signal.aborted) return;
        if (outcome === 'HELD' && view.hold_status === 'HELD' && view.requires_prepayment && view.obligation === null) {
          key.current ??= crypto.randomUUID();
          view = await clientPaymentsApi.open(scope, hold, key.current, csrf, signal);
        }
        if (!signal.aborted) setState(view);
      } catch (cause) {
        if (signal.aborted) return;
        const status = cause instanceof IntakeError ? cause.status : null;
        const code = cause instanceof IntakeError ? cause.code : null;
        if (status === 401) onExpired.current();
        if (code === 'NEEDS_CLARIFICATION') {
          setState({error: 'Согласуйте с клиентом точную сумму предоплаты.'});
        } else if (code === 'STALE_STATE') {
          setState({error: 'Удержание больше не действует.'});
        } else if (status === 403 || status === 404) {
          setState({error: 'Удержание недоступно.'});
        } else {
          setState({error: 'Не удалось прочитать предоплату.', retry: status !== 401});
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [workspace, business, conversation, client, request, quote, order, session, hold_id, allocation_id, outcome, csrf, retry]);

  useEffect(() => {
    const controller = new AbortController();
    checkoutScope.current = controller;
    const {signal} = controller;
    const scope = {workspace, business, conversation, client, request, quote, order, session};
    let timer: number | undefined;
    async function read() {
      try {
        const view = await clientPaymentsApi.checkout(scope, {hold_id, allocation_id}, signal);
        if (signal.aborted) return;
        setAttempt(view);
        if (view?.delivery === 'PENDING' || view?.delivery === 'DISPATCHING') {
          timer = window.setTimeout(() => void read(), 1500);
        }
      } catch (cause) {
        if (!signal.aborted && cause instanceof IntakeError && cause.status === 401) onExpired.current();
      }
    }
    setAttempt(null);
    setCheckoutError('');
    setReplacing(false);
    void read();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [workspace, business, conversation, client, request, quote, order, session, hold_id, allocation_id, outcome, retry]);

  async function replace(attempt: Checkout) {
    const signal = checkoutScope.current?.signal;
    if (!signal || signal.aborted || replacing) return;
    setReplacing(true);
    setCheckoutError('');
    if (replaceKey.current?.attempt !== attempt.id) {
      replaceKey.current = {attempt: attempt.id, key: crypto.randomUUID()};
    }
    try {
      const scope = {workspace, business, conversation, client, request, quote, order, session};
      await clientPaymentsApi.replaceCheckout(scope, {hold_id, allocation_id}, attempt.id, replaceKey.current.key, csrf, signal);
      if (!signal.aborted) setRetry(value => value + 1);
    } catch (cause) {
      if (signal.aborted) return;
      if (cause instanceof IntakeError && cause.status === 401) onExpired.current();
      setCheckoutError('Не удалось создать новую ссылку.');
    } finally {
      if (!signal.aborted) setReplacing(false);
    }
  }

  if (state === null) return outcome === 'HELD' ? <p role="status">Проверяем предоплату…</p> : null;
  if ('error' in state) return <div>
    <p role="alert">{state.error}</p>
    {state.retry && <button type="button" className="secondary" onClick={() => setRetry(value => value + 1)}>Повторить</button>}
  </div>;
  const payment = state.obligation;
  if (payment === null) return null;
  const price = payment.price_range === null
    ? `Цена ${money(payment.price_minor)} ₽`
    : `Предварительная цена ${money(payment.price_range.lower_minor)}–${money(payment.price_range.upper_minor)} ₽`;
  const deposit = {
    FIXED_DEPOSIT: 'фиксированная предоплата',
    FULL_PREPAYMENT: 'полная предоплата',
    PERCENT_DEPOSIT: `предоплата ${payment.percent}%`,
  }[payment.mode];
  const active = outcome === 'HELD' && state.hold_status === 'HELD';
  const deadline = Date.parse(expires_at) === Date.parse(state.expires_at) ? expires_at : state.expires_at;
  const checkout = attempt?.obligation_id === payment.id && attempt.hold_id === hold_id ? attempt : null;
  return <><p data-testid="payment-obligation" data-obligation-id={payment.id} data-payment-status={payment.status}>
    {price} · {deposit} {money(payment.amount_minor)} ₽ · {active && <>
      удержано до <time dateTime={state.expires_at}>{deadlineText(deadline)}</time> · </>
    }оплата ещё не получена
  </p>
    {checkout && <div data-testid="payment-checkout" data-attempt-id={checkout.id}>
      <p role="status">{checkoutMessage(checkout)}</p>
      {active && checkout.status === 'CANCELED' &&
        <button type="button" className="secondary" disabled={replacing} onClick={() => void replace(checkout)}>
          Создать новую ссылку
        </button>}
      {checkoutError && <p role="alert">{checkoutError}</p>}
    </div>}
  </>;
}
