import {useEffect, useState} from 'react';
import {IntakeError} from './intake-api';
import {schedulingApi} from './scheduling-api';
import type {Booking, SchedulingScope} from './scheduling-api';
import {timeInterval, utcOffset} from './SchedulingAvailability';

type Props = {scope: SchedulingScope; expired: () => void};
type Reading = {key: string} & ({booking: Booking | null} | {error: string});

function deadlineText(value: string) {
  return `${value.slice(0, 10)} ${value.slice(11, 19)} · ${utcOffset(value)}`;
}

function BookingDetails({booking}: {booking: Booking | null}) {
  if (booking === null) return <p>Время визита ещё не назначено.</p>;
  if (booking.outcome === 'EXPIRED') return <p>Срок удержания истёк.</p>;
  if (booking.outcome === 'RELEASED') return <p>Удержание снято.</p>;
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

export function SessionBooking({scope: {workspace, business, conversation, client, request, quote, order, session}, expired}: Props) {
  const key = [workspace, business, conversation, client, request, quote, order, session].join('/');
  const [reading, setReading] = useState<Reading | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const scope = {workspace, business, conversation, client, request, quote, order, session};
    void schedulingApi.booking(scope, controller.signal).then(({booking}) => {
      if (!controller.signal.aborted) setReading({key, booking});
    }).catch(cause => {
      if (controller.signal.aborted) return;
      const status = cause instanceof IntakeError ? cause.status : null;
      if (status === 401) expired();
      const error = status === 403 || status === 404 ? 'Работа недоступна. Откройте список работ заново.' :
        'Не удалось прочитать состояние записи.';
      setReading({key, error});
    });
    return () => controller.abort();
  }, [workspace, business, conversation, client, request, quote, order, session, key, expired]);

  const current = reading?.key === key ? reading : null;
  return <section className="session-booking" aria-label="Запись сейчас" aria-busy={current === null}>
    <h6>Запись сейчас</h6>
    <div aria-live="polite">
      {current === null ? <p>Проверяем состояние записи…</p> :
        'error' in current ? <p role="alert">{current.error}</p> : <BookingDetails booking={current.booking}/>}
    </div>
  </section>;
}
