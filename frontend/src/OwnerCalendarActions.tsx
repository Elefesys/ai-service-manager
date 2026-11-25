import {useEffect, useId, useRef, useState} from 'react';
import type {FormEvent} from 'react';
import {IntakeError} from './intake-api';
import {conflictMessage, ownerCalendarApi} from './owner-calendar-api';
import type {BusinessScope, MoveOffer} from './owner-calendar-api';
import {SchedulingError, timeInterval, utcOffset} from './scheduling-api';
import type {Booking, SchedulingScope} from './scheduling-api';

type CommandScope = {scope: BusinessScope; changed: () => void; expired: () => void};
type Attempt = {
  key: string;
  staleMessage?: string;
  run: (key: string, signal: AbortSignal) => Promise<void>;
  rejected?: () => void;
};

export function useCalendarCommand({scope, changed, expired}: CommandScope) {
  const controller = useRef<AbortController | null>(null);
  const [retry, setRetry] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => () => { controller.current?.abort(); }, []);

  async function send(attempt: Attempt) {
    if (controller.current) return;
    const current = new AbortController();
    const {signal} = current;
    controller.current = current;
    setBusy(true);
    setError('');
    try {
      await attempt.run(attempt.key, signal);
      if (!signal.aborted) setRetry(null);
    } catch (cause) {
      if (signal.aborted) return;
      const status = cause instanceof IntakeError ? cause.status : null;
      if (status === 401) {
        expired();
      } else if (status !== null && status < 500) {
        setRetry(null);
        attempt.rejected?.();
        if (cause instanceof SchedulingError && cause.code === 'CALENDAR_CONFLICT') {
          const message = await conflictMessage(scope, cause.affected, signal);
          if (!signal.aborted) setError(message);
        } else {
          setError(status === 409 ? (attempt.staleMessage ?? 'Запись или вариант уже изменились. Проверьте действующее время и начните действие заново.') :
            status === 422 || status === 400 ? 'Проверьте дату, время и причину.' : 'Действие недоступно. Откройте календарь заново.');
        }
      } else {
        setRetry(attempt);
        setError('Результат неизвестен. Можно повторить ту же команду.');
      }
    } finally {
      if (controller.current === current) controller.current = null;
      if (!signal.aborted) {
        setBusy(false);
        changed();
      }
    }
  }

  return {
    busy, locked: busy || retry !== null, error,
    start: (run: Attempt['run'], options: Pick<Attempt, 'rejected' | 'staleMessage'> = {}) => {
      if (!retry) void send({key: crypto.randomUUID(), run, ...options});
    },
    reset: () => setError(''),
    repeat: retry ? () => void send(retry) : null,
  };
}

export function CalendarCommandFeedback({command}: {command: ReturnType<typeof useCalendarCommand>}) {
  return <>
    {command.error && <p role="alert" className="error">{command.error}</p>}
    {command.repeat && <button className="secondary" type="button" disabled={command.busy} onClick={command.repeat}>Повторить ту же команду</button>}
  </>;
}

type AppointmentForm =
  | {type: 'move'; appointment: string; date: string; offer: MoveOffer | null; option: string}
  | {type: 'cancel'; appointment: string};

export function OwnerAppointmentActions({scope, booking, date, csrf, changed, expired}: CommandScope & {
  scope: SchedulingScope; booking: Booking | null; date: string; csrf: string;
}) {
  const command = useCalendarCommand({scope, changed, expired});
  const [form, setForm] = useState<AppointmentForm | null>(null);
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');
  const timesId = useId();
  const current = booking?.outcome === 'CONFIRMED' ? booking : null;

  function open(type: AppointmentForm['type']) {
    if (!current) return;
    setReason('');
    setNotice('');
    command.reset();
    setForm(type === 'move'
      ? {type, appointment: current.appointment_id, date, offer: null, option: ''}
      : {type, appointment: current.appointment_id});
  }

  function findOptions() {
    if (form?.type !== 'move' || !form.date) return;
    setNotice('');
    command.start(async (key, signal) => {
      const offer = await ownerCalendarApi.moveOffer(scope, form.appointment, form.date, key, csrf, signal);
      if (!signal.aborted) setForm({...form, offer, option: ''});
    }, {rejected: () => setForm(null)});
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!form || !reason.trim() || command.locked || (form.type === 'move' && !form.option)) return;
    const change = form.type === 'move' ? {reason: reason.trim(), option_id: form.option} : {reason: reason.trim()};
    command.start(async (key, signal) => {
      const updated = await ownerCalendarApi.changeAppointment(scope, form.appointment, change, key, csrf, signal);
      if (!signal.aborted) {
        setNotice(updated.outcome === 'CANCELLED' ? 'Визит отменён.' : 'Время визита сохранено.');
        setForm(null);
        setReason('');
      }
    }, {rejected: () => setForm(null)});
  }

  return <div className="calendar-controls">
    {current && !form && <div className="control-actions">
      <button className="secondary" type="button" disabled={command.locked} onClick={() => open('move')}>Перенести визит</button>
      <button className="secondary" type="button" disabled={command.locked} onClick={() => open('cancel')}>Отменить визит</button>
    </div>}
    {form && <form onSubmit={submit}>
      <fieldset className="form" aria-label={form.type === 'move' ? 'Перенос визита' : 'Отмена визита'} disabled={command.locked}>
        {form.type === 'move' && <>
          <label>Дата переноса<input type="date" required value={form.date} onChange={event =>
            setForm({...form, date: event.target.value, offer: null, option: ''})}/></label>
          <button className="secondary" type="button" disabled={!form.date} onClick={findOptions}>Подобрать время переноса</button>
          {form.offer && form.offer.options.length === 0 && <p role="status">Подходящих окон для переноса нет.</p>}
          {form.offer && form.offer.options.length > 0 && <>
            <label htmlFor={timesId}>Новое время</label>
            <select id={timesId} required value={form.option} onChange={event => setForm({...form, option: event.target.value})}>
              <option value="">Выберите окно</option>
              {form.offer.options.map(option => <option key={option.option_id} value={option.option_id}>
                {timeInterval(option.visit_start, option.visit_end, form.date)}
              </option>)}
            </select>
          </>}
        </>}
        <label>{form.type === 'move' ? 'Причина переноса' : 'Причина отмены'}
          <input required maxLength={300} value={reason} onChange={event => setReason(event.target.value)}/>
        </label>
        <div className="control-actions">
          <button className={form.type === 'cancel' ? 'danger' : undefined} type="submit"
            disabled={!reason.trim() || (form.type === 'move' && !form.option)}>
            {form.type === 'move' ? 'Подтвердить перенос' : 'Подтвердить отмену'}
          </button>
          <button className="secondary" type="button" onClick={() => { setForm(null); command.reset(); }}>Закрыть форму</button>
        </div>
      </fieldset>
    </form>}
    {notice && <p role="status">{notice}</p>}
    <CalendarCommandFeedback command={command}/>
  </div>;
}

function localChoices(value: string, timezone: string): string[] {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return [];
  const wall = Date.parse(`${value}:00Z`);
  if (!Number.isFinite(wall)) return [];
  const format = new Intl.DateTimeFormat('sv-SE', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', timeZoneName: 'longOffset',
  });
  const options = new Set<string>();
  // Check the offsets on either side of a possible clock change.
  for (const distance of [-86400000, 0, 86400000]) {
    const label = format.formatToParts(wall + distance).find(part => part.type === 'timeZoneName')?.value;
    const offset = label === 'GMT' ? '+00:00' : label?.slice(3);
    if (!offset) continue;
    const instant = `${value}:00${offset}`;
    if (format.format(Date.parse(instant)).replace(' ', 'T').startsWith(value)) options.add(instant);
  }
  return [...options];
}

export function OwnerBlockForm({timezone, date, busy, place}: {
  timezone: string; date: string; busy: boolean; place: (block: {start: string; end: string}) => void;
}) {
  const [start, setStart] = useState(`${date}T09:00`);
  const [end, setEnd] = useState(`${date}T09:15`);
  const [startOffset, setStartOffset] = useState('');
  const [endOffset, setEndOffset] = useState('');
  const [error, setError] = useState('');
  const starts = localChoices(start, timezone);
  const ends = localChoices(end, timezone);
  const startInstant = starts.length === 1 ? starts[0] : starts.find(choice => choice === startOffset);
  const endInstant = ends.length === 1 ? ends[0] : ends.find(choice => choice === endOffset);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!startInstant || !endInstant || Date.parse(startInstant) >= Date.parse(endInstant)) {
      setError('Выберите существующее местное время. Конец блока должен быть позже начала.');
      return;
    }
    setError('');
    place({start: startInstant, end: endInstant});
  }
  return <details>
    <summary>Поставить блок</summary>
    <form onSubmit={submit}>
      <fieldset className="form" disabled={busy} aria-label="Новый блок">
        <label>Начало блока<input type="datetime-local" required value={start} onChange={event => { setStart(event.target.value); setStartOffset(''); }}/></label>
        {starts.length > 1 && <label>Смещение начала<select required value={startOffset} onChange={event => setStartOffset(event.target.value)}>
          <option value="">Выберите смещение</option>
          {starts.map(choice => <option value={choice} key={choice}>{utcOffset(choice)}</option>)}
        </select></label>}
        <label>Конец блока<input type="datetime-local" required value={end} onChange={event => { setEnd(event.target.value); setEndOffset(''); }}/></label>
        {ends.length > 1 && <label>Смещение конца<select required value={endOffset} onChange={event => setEndOffset(event.target.value)}>
          <option value="">Выберите смещение</option>
          {ends.map(choice => <option value={choice} key={choice}>{utcOffset(choice)}</option>)}
        </select></label>}
        <button type="submit">Сохранить блок</button>
      </fieldset>
      {error && <p role="alert" className="error">{error}</p>}
    </form>
  </details>;
}
