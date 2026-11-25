import {useEffect, useRef, useState} from 'react';
import type {ReactNode} from 'react';
import {IntakeError} from './intake-api';
import {schedulingApi, timeInterval, utcOffset} from './scheduling-api';
import type {Booking, SessionBookingView, SchedulingScope} from './scheduling-api';

type Props = {scope: SchedulingScope; expired: () => void; refresh?: number; actions?: (booking: Booking | null) => ReactNode};
type Reading = {key: string} & ({view: SessionBookingView} | {error: string});

export function deadlineText(value: string) {
  return `${value.slice(0, 10)} ${value.slice(11, 19)} · ${utcOffset(value)}`;
}

function BookingDetails({booking}: {booking: Booking | null}) {
  if (booking === null) return <p>Время визита ещё не назначено.</p>;
  if (booking.outcome === 'EXPIRED') return <p>Срок удержания истёк.</p>;
  if (booking.outcome === 'RELEASED') return <p>Удержание снято.</p>;
  if (booking.outcome === 'CANCELLED') return <p>Запись отменена.</p>;
  return <>
    <p>{booking.outcome === 'CONFIRMED' ? 'Запись подтверждена.' :
      <>Время удержано до <time dateTime={booking.expires_at}>{deadlineText(booking.expires_at)}</time>, запись не подтверждена.</>}</p>
    <dl className="billing-facts">
      <dt>Дата визита</dt><dd>{booking.date}</dd>
      <dt>Время визита</dt><dd>{timeInterval(booking.visit_start, booking.visit_end, booking.date)}</dd>
      <dt>Часовой пояс</dt><dd>{booking.timezone}</dd>
      <dt>Занятость с буферами</dt><dd>{timeInterval(booking.busy_start, booking.busy_end, booking.date)}</dd>
    </dl>
  </>;
}

function BookingHistory({history}: Pick<SessionBookingView, 'history'>) {
  if (!history.length) return null;
  return <details>
    <summary>История записи</summary>
    <ul>
      {history.map(entry => <li key={entry.appointment_id}>
        <p>{entry.date} · {timeInterval(entry.visit_start, entry.visit_end, entry.date)} · {entry.timezone}</p>
        <p>Отменена <time dateTime={entry.cancelled_at}>{deadlineText(entry.cancelled_at)}</time></p>
        <p>{entry.cancel_reason}</p>
      </li>)}
    </ul>
  </details>;
}

export function SessionBooking({scope: {workspace, business, conversation, client, request, quote, order, session}, expired, refresh = 0, actions}: Props) {
  const key = [workspace, business, conversation, client, request, quote, order, session].join('/');
  const [reading, setReading] = useState<Reading | null>(null);

  const onExpired = useRef(expired);
  onExpired.current = expired;
  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    const scope = {workspace, business, conversation, client, request, quote, order, session};
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      if (signal.aborted) return;
      try {
        const view = await schedulingApi.booking(scope, signal);
        if (!signal.aborted) setReading({key, view});
      } catch (cause) {
        if (signal.aborted) return;
        const status = cause instanceof IntakeError ? cause.status : null;
        if (status === 401) onExpired.current();
        const error = status === 403 || status === 404 ? 'Работа недоступна. Откройте список работ заново.' :
          'Не удалось прочитать состояние записи.';
        setReading({key, error});
        if (status === 401 || status === 403 || status === 404) return;
      }
      if (!signal.aborted) timer = setTimeout(load, 4000);
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [workspace, business, conversation, client, request, quote, order, session, key, refresh]);

  const current = reading?.key === key ? reading : null;
  const booking = current && 'view' in current ? current.view.booking : null;
  return <section className="session-booking" aria-label="Запись сейчас" aria-busy={current === null}
    data-session-id={session} data-booking-id={booking ? ('appointment_id' in booking ? booking.appointment_id : booking.hold_id) : undefined}
    data-booking-status={booking?.outcome}>
    <h6>Запись сейчас</h6>
    <div aria-live="polite">
      {current === null ? <p>Проверяем состояние записи…</p> :
        'error' in current ? <p role="alert">{current.error}</p> : <>
          <BookingDetails booking={current.view.booking}/>
          <BookingHistory history={current.view.history}/>
          {actions?.(current.view.booking)}
        </>}
    </div>
  </section>;
}
