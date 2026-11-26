import {useEffect, useId, useRef, useState} from 'react';
import type {FormEvent} from 'react';
import {conflictMessage} from './owner-calendar-api';
import {IntakeError} from './intake-api';
import {policyFields, policyLimits, SchedulingError, schedulingApi, timeInterval} from './scheduling-api';
import type {Availability, DayInterval, PolicyField, PolicySettings, ScheduleChange, ScheduleCommand, SchedulingScope} from './scheduling-api';

const weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
const policyLabels: Record<PolicyField, string> = {
  step_minutes: 'Шаг начала, мин',
  buffer_before_minutes: 'Буфер до сеанса, мин',
  buffer_after_minutes: 'Буфер после сеанса, мин',
  minimum_notice_minutes: 'Минимальное предупреждение, мин',
  horizon_days: 'Горизонт, дни',
  offer_ttl_minutes: 'Срок варианта, мин',
  hold_ttl_minutes: 'Срок удержания, мин',
};
const emptyMessage: Record<NonNullable<Availability['reason']>, string> = {
  NO_WORKING_HOURS: 'Рабочие часы на эту дату не заданы.',
  NO_ACTIVE_POLICY: 'Активируйте правила подбора времени для этой услуги.',
  DURATION_UNAVAILABLE: 'Длительность согласованного сеанса не подтверждена.',
  DATE_CLOSED: 'На эту дату отмечен выходной.',
  NO_WINDOWS: 'Подходящих окон на эту дату нет.',
};

type IntervalInput = {weekday: number; start: string; end: string};
type SettingsProps = {view: Availability; busy: boolean; save: (change: ScheduleChange) => void};
export type CalendarAvailability = {date: string; version: string; changed: () => void};
type Props = {scope: SchedulingScope; csrf: string; workName?: string; expired: () => void; calendar?: CalendarAvailability};

function clockText(minute: number) {
  return `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
}

function minuteValue(value: string) {
  const [hour, minute] = value.split(':').map(Number);
  return hour * 60 + minute;
}

function intervalValue(input: IntervalInput): DayInterval {
  return {start_minute: minuteValue(input.start), end_minute: minuteValue(input.end)};
}

function intervalInput(interval: DayInterval, weekday = 0): IntervalInput {
  return {weekday, start: clockText(interval.start_minute), end: clockText(interval.end_minute)};
}

function Intervals({items, onChange, weekly}: {
  items: IntervalInput[];
  onChange: (items: IntervalInput[]) => void;
  weekly?: boolean;
}) {
  function edit(index: number, patch: Partial<IntervalInput>) {
    onChange(items.map((item, i) => i === index ? {...item, ...patch} : item));
  }

  return <>
    {items.map((item, index) => <div className="scheduling-interval" role="group" aria-label={`Интервал ${index + 1}`} key={index}>
      {weekly && <label>День недели<select value={item.weekday} onChange={event => edit(index, {weekday: Number(event.target.value)})}>
        {weekdays.map((name, day) => <option key={name} value={day}>{name}</option>)}
      </select></label>}
      <label>Начало<input required maxLength={5} pattern="(?:[01][0-9]|2[0-3]):[0-5][0-9]" placeholder="ЧЧ:ММ" value={item.start}
        onChange={event => edit(index, {start: event.target.value})}/></label>
      <label>Окончание<input required maxLength={5} pattern="(?:(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00)" placeholder="ЧЧ:ММ" value={item.end}
        onChange={event => edit(index, {end: event.target.value})}/></label>
      <button className="secondary" type="button" onClick={() => onChange(items.filter((_, i) => i !== index))}>Удалить интервал</button>
    </div>)}
    <button className="secondary" type="button" onClick={() => onChange([...items, {weekday: items.at(-1)?.weekday ?? 0, start: '', end: ''}])}>Добавить интервал</button>
  </>;
}

function WorkingHours({view, busy, save}: SettingsProps) {
  const [timezone, setTimezone] = useState(view.timezone ?? '');
  const [intervals, setIntervals] = useState(() => view.week.map(item => intervalInput(item, item.weekday)));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !timezone.trim()) return;
    save({action: 'schedule', timezone: timezone.trim(), week: intervals.map(item => ({weekday: item.weekday, ...intervalValue(item)}))});
  }

  return <details open={view.timezone === null}>
    <summary>Рабочие часы</summary>
    <form onSubmit={submit}>
      <fieldset className="form" disabled={busy} aria-label="Рабочая неделя">
        <label>Часовой пояс<input required maxLength={128} placeholder="Asia/Novosibirsk" value={timezone} onChange={event => setTimezone(event.target.value)}/></label>
        <Intervals items={intervals} onChange={setIntervals} weekly/>
        <button type="submit">Сохранить рабочие часы</button>
      </fieldset>
    </form>
  </details>;
}

function Policy({view, busy, save}: SettingsProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values = Object.fromEntries(policyFields.map(field => [field, Number(data.get(field))])) as PolicySettings;
    if (!busy && view.resource_id) save({action: 'policy', ...values});
  }

  return <details>
    <summary>Правила подбора времени</summary>
    <form onSubmit={submit}>
      <fieldset className="form" disabled={busy || !view.resource_id} aria-label="Настройки подбора времени">
        {!view.resource_id && <p>Сначала сохраните рабочие часы.</p>}
        {policyFields.map(field => <label key={field}>{policyLabels[field]}
          <input required type="number" step={1} name={field} min={policyLimits[field][0]} max={policyLimits[field][1]} defaultValue={view.policy?.[field] ?? ''}/>
        </label>)}
        <button type="submit">Активировать правила</button>
      </fieldset>
    </form>
  </details>;
}

function DateException({view, busy, save}: SettingsProps) {
  const [intervals, setIntervals] = useState(() => (view.exception?.windows ?? []).map(item => intervalInput(item)));
  const closed = view.exception?.windows.length === 0;

  return <div className="scheduling-exception">
    <div className="control-actions">
      <button className="secondary" type="button" disabled={busy || closed} onClick={() => save({action: 'exception', date: view.date, windows: []})}>Отметить выходной</button>
      {view.exception && <button className="secondary" type="button" disabled={busy} onClick={() => save({action: 'exception', date: view.date, windows: null})}>Вернуть часы недели</button>}
    </div>
    <details>
      <summary>Задать часы на эту дату</summary>
      <form onSubmit={event => {
        event.preventDefault();
        if (!busy && intervals.length) save({action: 'exception', date: view.date, windows: intervals.map(intervalValue)});
      }}>
        <fieldset className="form" disabled={busy} aria-label="Часы на выбранную дату">
          <Intervals items={intervals} onChange={setIntervals}/>
          <button type="submit" disabled={!intervals.length}>Сохранить часы на дату</button>
        </fieldset>
      </form>
    </details>
  </div>;
}

function AvailabilityPanel({scope, workName, csrf, expired, id, calendar}: Props & {id: string}) {
  const active = useRef<AbortController | null>(null);
  const [view, setView] = useState<Availability | null>(null);
  const [date, setDate] = useState(calendar?.date ?? '');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [formReset, setFormReset] = useState(0);

  async function load(day?: string, command?: ScheduleCommand, background = false) {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    const {signal} = controller;
    if (!background) { setBusy(true); setError(''); }
    let reloading = false;
    try {
      let result: Availability;
      try {
        result = command && day
          ? await schedulingApi.change(scope, day, command, csrf, signal)
          : await schedulingApi.preview(scope, day, signal);
      } catch (cause) {
        if (signal.aborted || !command || !(cause instanceof IntakeError) ||
            cause.status !== 409 || cause.code !== 'STALE_STATE') throw cause;
        reloading = true;
        result = await schedulingApi.preview(scope, day, signal);
      }
      if (signal.aborted) return;
      setView(result);
      setDate(result.date);
      if (reloading) {
        setFormReset(value => value + 1);
        setError('Расписание уже изменилось. Проверьте сохранённые значения перед новой правкой.');
      }
    } catch (cause) {
      if (signal.aborted) return;
      const status = cause instanceof IntakeError ? cause.status : null;
      if (calendar && command && cause instanceof SchedulingError && cause.code === 'CALENDAR_CONFLICT' && day) {
        const message = await conflictMessage(scope, cause.affected, signal);
        if (!signal.aborted) setError(message);
        return;
      }
      if (!command || reloading || status !== 422) setView(null);
      if (status === 401) expired();
      setError(status === 403 || status === 404 ? 'Сеанс недоступен. Откройте карточку работы заново.' :
        status === 422 ? 'Проверьте дату и значения настроек.' : 'Не удалось получить актуальное расписание. Обновите варианты.');
    } finally {
      if (active.current === controller) {
        active.current = null;
        if (!signal.aborted) {
          setBusy(false);
          if (command) calendar?.changed();
        }
      }
    }
  }

  useEffect(() => {
    void load(calendar?.date);
    return () => {active.current?.abort(); active.current = null;};
  }, []);
  useEffect(() => {
    if (calendar) void load(calendar.date, undefined, true);
  }, [calendar?.version]);

  const save = (change: ScheduleChange) => {
    if (view && view.date === date) void load(view.date, {...change, expected_version: view.schedule_version});
  };

  return <section id={id} className="scheduling-availability" aria-label="Варианты времени выбранного сеанса" aria-busy={busy}>
    {view && <p>{workName && <><strong>{workName}</strong> · </>}{view.service_name}{view.occupied_minutes !== null && ` · ${view.occupied_minutes} мин`}</p>}
    <div className="scheduling-day">
      {!calendar && <label>Дата вариантов<input type="date" disabled={busy} value={date} onChange={event => {
        const day = event.target.value;
        setDate(day);
        if (day) void load(day);
      }}/></label>}
      {view?.timezone && <span>{view.timezone}</span>}
      <button className="secondary" disabled={busy} type="button" onClick={() => void load(date || undefined)}>Обновить варианты</button>
    </div>
    {busy && <p role="status">Проверяем расписание…</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {view && view.date === date && <>
      {!busy && (view.reason ? <p role="status">{emptyMessage[view.reason]}</p> : <ol aria-label="Подходящие окна" className="scheduling-windows">
        {view.windows.map(window => <li key={window.visit_start}>
          <strong>Визит {timeInterval(window.visit_start, window.visit_end, view.date)}</strong>
          <span>Занятость {timeInterval(window.busy_start, window.busy_end, view.date)}</span>
        </li>)}
      </ol>)}
      {view.resource_id && <DateException key={JSON.stringify([formReset, view.date, view.exception])} view={view} busy={busy} save={save}/>}
      <WorkingHours key={JSON.stringify([formReset, view.timezone, view.week])} view={view} busy={busy} save={save}/>
      <Policy key={JSON.stringify([formReset, view.policy?.policy_id])} view={view} busy={busy} save={save}/>
    </>}
  </section>;
}

export function SchedulingAvailability(props: Props) {
  const [opened, setOpened] = useState(false);
  const id = useId();
  return <>
    <button className="secondary" type="button" aria-expanded={opened} aria-controls={opened ? id : undefined} onClick={() => setOpened(!opened)}>
      {opened ? 'Скрыть варианты времени' : 'Варианты времени'}
    </button>
    {opened && <AvailabilityPanel key={props.calendar?.date} {...props} id={id}/>}
  </>;
}
