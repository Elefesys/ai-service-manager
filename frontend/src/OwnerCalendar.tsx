import {useEffect, useId, useRef, useState} from 'react';
import {IntakeError} from './intake-api';
import {CalendarCommandFeedback, OwnerBlockForm, useCalendarCommand} from './OwnerCalendarActions';
import {entryId, ownerCalendarApi, workScope} from './owner-calendar-api';
import type {BusinessScope, CalendarEntry, OwnerDay, WorkEntry} from './owner-calendar-api';
import {OwnerCalendarWork} from './OwnerCalendarWork';
import {timeInterval} from './SchedulingAvailability';
import {deadlineText} from './SessionBooking';
import {dateValue} from './scheduling-api';
import type {SchedulingScope} from './scheduling-api';

const statusLabels = {
  CONFIRMED: 'Запись подтверждена',
  HELD: 'Время удержано',
  CANCELLED: 'Запись отменена',
  EXPIRED: 'Срок удержания истёк',
  RELEASED: 'Удержание снято',
};

function calendarDate(date: string, days: number): string {
  const next = new Date(`${date}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + days);
  return next.toISOString().slice(0, 10);
}

function clock(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}

function readDelay(day: OwnerDay) {
  const deadlines = day.entries.flatMap(row =>
    row.kind === 'HOLD' ? [Date.parse(row.booking.expires_at) - Date.parse(day.now)] : []);
  return Math.max(250, Math.min(4000, ...deadlines.map(ms => ms + 50)));
}

function useOwnerDay(scope: BusinessScope, date: string, refresh: number, expired: () => void) {
  const [reading, setReading] = useState<{key: string; day: OwnerDay | null; error: string} | null>(null);
  const key = `${scope.workspace}/${scope.business}/${date}`;

  useEffect(() => {
    const controller = new AbortController();
    const {signal} = controller;
    let timer: ReturnType<typeof setTimeout>;

    async function load() {
      if (signal.aborted) return;
      let delay = 4000;
      try {
        const day = await ownerCalendarApi.day(scope, date || undefined, signal);
        if (signal.aborted) return;
        setReading({key, day, error: ''});
        delay = readDelay(day);
      } catch (cause) {
        if (signal.aborted) return;
        const status = cause instanceof IntakeError ? cause.status : null;
        if (status === 401) expired();
        const denied = status === 401 || status === 403 || status === 404;
        setReading({key, day: null, error: denied ? 'Календарь этого бизнеса недоступен.' : 'Не удалось прочитать день календаря.'});
        if (denied) return;
      }
      if (!signal.aborted) timer = setTimeout(load, delay);
    }

    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [scope, key, date, refresh, expired]);

  return reading?.key === key ? reading : null;
}

function CalendarRow({row, date, open, follow, release, busy}: {
  row: CalendarEntry; date: string; open: (row: WorkEntry) => void;
  follow: (row: WorkEntry, date: string, id: string) => void; release: (id: string) => void; busy: boolean;
}) {
  const id = entryId(row);
  if (row.kind === 'BLOCK') return <li className="calendar-row" data-testid={`calendar-entry-${id}`} data-status="BLOCKED">
    <div><strong>Блок</strong><div>{timeInterval(row.start, row.end, date)}</div></div>
    <button className="secondary" type="button" disabled={busy} onClick={() => release(row.block_id)}>Снять блок</button>
  </li>;
  const {booking, selection, work_label} = row;
  const successor = row.kind === 'APPOINTMENT' ? row.successor : null;
  return <li className="calendar-row" id={`calendar-entry-${id}`} tabIndex={-1} data-testid={`calendar-entry-${id}`}
    data-request-id={selection.request_id} data-session-id={selection.session_id} data-status={booking.outcome}>
    <div>
      <strong>{work_label}</strong>
      <span className="muted"> · Клиент №{selection.client_id.slice(0, 8)}</span>
      <p>{successor ? 'Запись перенесена' : statusLabels[booking.outcome]}</p>
      <div>Визит {timeInterval(booking.visit_start, booking.visit_end, date)}</div>
      <div className="muted">Занятость {timeInterval(booking.busy_start, booking.busy_end, date)}</div>
      {booking.outcome === 'HELD' && <div>До <time dateTime={booking.expires_at}>{deadlineText(booking.expires_at)}</time></div>}
      {booking.outcome === 'CANCELLED' && <p className="muted">Причина {booking.cancel_reason}</p>}
    </div>
    <div className="calendar-row-actions">
      <button className="secondary" type="button" onClick={() => open(row)}>Открыть работу</button>
      {successor && <button className="secondary" type="button" onClick={() => follow(row, successor.date, successor.appointment_id)}>Показать новый визит</button>}
    </div>
  </li>;
}

function DayEntries({scope, day, csrf, changed, expired, open, follow}: {
  scope: BusinessScope; day: OwnerDay; csrf: string; changed: () => void; expired: () => void;
  open: (row: WorkEntry) => void; follow: (row: WorkEntry, date: string, id: string) => void;
}) {
  const {date, timezone} = day;
  const command = useCalendarCommand({scope, changed, expired});
  const release = (id: string) => command.start((key, signal) => ownerCalendarApi.changeBlock(scope, {release: id}, key, csrf, signal), [date]);
  const place = (block: {start: string; end: string}) => command.start(
    (key, signal) => ownerCalendarApi.changeBlock(scope, block, key, csrf, signal), [block.start.slice(0, 10), block.end.slice(0, 10)]);
  const row = (entry: CalendarEntry) => <CalendarRow key={entryId(entry)} row={entry} date={date} open={open} follow={follow} release={release} busy={command.locked}/>;

  if (!timezone) return <p>Расписание мастера ещё не настроено.</p>;
  return <>
    {day.working_intervals.length > 0 ? <p>Рабочие часы {day.working_intervals.map(interval =>
      `${clock(interval.start_minute)}–${clock(interval.end_minute)}`).join(', ')}</p> : <p>Выходной.</p>}
    <OwnerBlockForm date={date} timezone={timezone} busy={command.locked} place={place}/>
    <CalendarCommandFeedback command={command}/>
    {day.entries.length > 0 ? <ul className="calendar-entries" aria-label="Занятость дня">{day.entries.map(row)}</ul> :
      <p role="status">На этот день нет действующей занятости.</p>}
    {day.history.length > 0 && <section aria-label="История календаря">
      <h3>История</h3><ul className="calendar-entries">{day.history.map(row)}</ul>
    </section>}
  </>;
}

function CalendarPanel({scope, csrf, expired, id}: {
  scope: BusinessScope; csrf: string; expired: () => void; id: string;
}) {
  const [date, setDate] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [work, setWork] = useState<{id: string; scope: SchedulingScope; label: string} | null>(null);
  const [followed, setFollowed] = useState<string | null>(null);
  const reading = useOwnerDay(scope, date, refresh, expired);
  const day = reading?.day ?? null;
  const shownDate = date || day?.date || '';
  const changed = () => setRefresh(current => current + 1);
  const open = (row: WorkEntry) => setWork({id: entryId(row), scope: workScope(scope, row), label: row.work_label});

  useEffect(() => {
    if (!day || !followed) return;
    const target = document.getElementById(`calendar-entry-${followed}`);
    if (target) {
      target.focus({preventScroll: true});
      target.scrollIntoView?.({block: 'nearest'});
      setFollowed(null);
    }
  }, [day, followed]);

  return <div id={id}>
    <div className="calendar-day-controls">
      <label>Дата календаря<input type="date" value={shownDate} onChange={event => {
        if (dateValue(event.target.value)) { setFollowed(null); setDate(event.target.value); }
      }}/></label>
      <div className="control-actions">
        <button className="secondary" type="button" disabled={!shownDate} onClick={() => setDate(calendarDate(shownDate, -1))}>Предыдущий день</button>
        <button className="secondary" type="button" disabled={!shownDate} onClick={() => setDate(calendarDate(shownDate, 1))}>Следующий день</button>
      </div>
      {day?.timezone && <span>{day.timezone}</span>}
    </div>
    {!reading && <p role="status">Загружаем день…</p>}
    {reading?.error && <p role="alert" className="error">{reading.error}</p>}
    {day && <DayEntries key={day.date} scope={scope} day={day} csrf={csrf} changed={changed} expired={expired}
      open={open} follow={(row, nextDate, nextId) => { open(row); setDate(nextDate); setFollowed(nextId); }}/>}
    {work && shownDate && !reading?.error && <OwnerCalendarWork key={work.id} scope={work.scope} label={work.label} date={shownDate}
      version={day ? JSON.stringify([day.schedule_version, day.entries]) : ''} csrf={csrf} refresh={refresh}
      changed={changed} expired={expired} close={() => setWork(null)}/>}
  </div>;
}

export function OwnerCalendar({scope, csrf, expired}: {scope: BusinessScope; csrf: string; expired: () => void}) {
  const [opened, setOpened] = useState(false);
  const id = useId();
  return <section className="panel owner-calendar" aria-label="Календарь мастера">
    <div className="billing-heading">
      <h2>Календарь</h2>
      <button type="button" className="secondary" aria-expanded={opened} aria-controls={id} onClick={() => setOpened(!opened)}>
        {opened ? 'Закрыть календарь' : 'Открыть календарь'}
      </button>
    </div>
    {opened && <CalendarPanel scope={scope} csrf={csrf} expired={expired} id={id}/>}
  </section>;
}
