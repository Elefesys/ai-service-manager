import {useEffect, useRef, useState} from 'react';
import {clientPaymentsApi} from './client-payments-api';
import type {HoldPayment} from './client-payments-api';
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

export function PaymentObligation({
  scope: {workspace, business, conversation, client, request, quote, order, session},
  booking: {hold_id, allocation_id, outcome, expires_at}, expired, csrf,
}: Props) {
  const [state, setState] = useState<State | null>(null);
  const [retry, setRetry] = useState(0);
  const key = useRef<string>(null);
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
  return <p data-testid="payment-obligation" data-obligation-id={payment.id} data-payment-status={payment.status}>
    {price} · {deposit} {money(payment.amount_minor)} ₽ · {active && <>
      удержано до <time dateTime={state.expires_at}>{deadlineText(deadline)}</time> · </>
    }оплата ещё не получена
  </p>;
}
