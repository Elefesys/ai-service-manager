import {
  businessPath, checkIntervals, checkWindow, dateValue, instant, integer, invalid, object, parseBooking,
  record, schedulingRequest, sessionPath, sessionReferences, timestamps, uuid,
} from './scheduling-api';
import type {AffectedAllocation, Booking, DayInterval, SchedulingScope, Slot} from './scheduling-api';

export type BusinessScope = Pick<SchedulingScope, 'workspace' | 'business'>;
type Selection = {client_id: string; conversation_id: string; request_id: string; quote_id: string; order_id: string; session_id: string};
type Work = {selection: Selection; work_label: string};
export type WorkEntry =
  | (Work & {kind: 'APPOINTMENT'; booking: Extract<Booking, {appointment_id: string}>; successor: {appointment_id: string; date: string} | null})
  | (Work & {kind: 'HOLD'; booking: Extract<Booking, {expires_at: string}>});
export type CalendarEntry = WorkEntry | {kind: 'BLOCK'; block_id: string; start: string; end: string};
export type OwnerDay = {
  date: string;
  now: string;
  timezone: string | null;
  resource_id: string | null;
  schedule_version: number;
  working_intervals: DayInterval[];
  exception: {date: string; windows: DayInterval[]} | null;
  entries: CalendarEntry[];
  history: WorkEntry[];
};
export type MoveOption = Slot & {option_id: string};
export type MoveOffer = {offer_id: string | null; date: string; timezone: string | null; expires_at: string | null; options: MoveOption[]};

function parseEntry(value: unknown, resource: unknown, historical: boolean): CalendarEntry {
  if (!record(value)) return invalid();
  if (value.kind === 'BLOCK') {
    const row = object(value, ['kind', 'block_id', 'start', 'end']);
    if (historical || !uuid(row.block_id) || !instant(row.start) || !instant(row.end) ||
        Date.parse(row.start) >= Date.parse(row.end)) return invalid();
    return row as CalendarEntry;
  }
  const appointment = value.kind === 'APPOINTMENT';
  const row = object(value, ['kind', 'selection', 'work_label', 'booking', ...(appointment ? ['successor'] : [])]);
  const selection = object(row.selection, ['client_id', 'conversation_id', 'request_id', 'quote_id', 'order_id', 'session_id']);
  const booking = parseBooking(row.booking);
  if (!Object.values(selection).every(uuid) || typeof row.work_label !== 'string' || !row.work_label.trim() ||
      booking.resource_id !== resource) return invalid();
  if (appointment) {
    if (booking.outcome !== (historical ? 'CANCELLED' : 'CONFIRMED')) return invalid();
    if (row.successor !== null) {
      const successor = object(row.successor, ['appointment_id', 'date']);
      if (!historical || !uuid(successor.appointment_id) || !dateValue(successor.date) ||
          successor.appointment_id === booking.appointment_id) return invalid();
    }
  } else if (row.kind !== 'HOLD' || (historical ? booking.outcome !== 'EXPIRED' && booking.outcome !== 'RELEASED' : booking.outcome !== 'HELD')) {
    return invalid();
  }
  return row as WorkEntry;
}

export function parseOwnerDay(value: unknown, date?: string): OwnerDay {
  const day = object(value, ['date', 'now', 'timezone', 'resource_id', 'schedule_version', 'working_intervals', 'exception', 'entries', 'history']);
  if (!dateValue(day.date) || (date && date !== day.date) || !instant(day.now) ||
      !integer(day.schedule_version, 0, Number.MAX_SAFE_INTEGER) || !Array.isArray(day.entries) || !Array.isArray(day.history)) return invalid();
  if (day.resource_id === null) {
    if (day.timezone !== null || day.schedule_version !== 0 || day.exception !== null ||
        day.entries.length || day.history.length || !Array.isArray(day.working_intervals) || day.working_intervals.length) return invalid();
  } else {
    if (!uuid(day.resource_id) || typeof day.timezone !== 'string' || !day.timezone || day.schedule_version === 0) return invalid();
    // Validate the zone before it reaches local-date and datetime controls.
    try { new Intl.DateTimeFormat('ru', {timeZone: day.timezone}); } catch { return invalid(); }
  }
  checkIntervals(day.working_intervals, false);
  if (day.exception !== null) {
    const exception = object(day.exception, ['date', 'windows']);
    if (exception.date !== day.date) return invalid();
    checkIntervals(exception.windows, false);
  }
  const entries = day.entries.map(row => parseEntry(row, day.resource_id, false));
  const history = day.history.map(row => parseEntry(row, day.resource_id, true) as WorkEntry);
  const ids = [...entries, ...history].map(entryId);
  if (new Set(ids).size !== ids.length) return invalid();
  return {...day, entries, history} as OwnerDay;
}

function zonedInstant(value: unknown, format: Intl.DateTimeFormat): string {
  if (!instant(value)) return invalid();
  const parts = Object.fromEntries(format.formatToParts(Date.parse(value)).map(({type, value}) => [type, value]));
  const offset = parts.timeZoneName === 'GMT' ? '+00:00' : parts.timeZoneName.slice(3);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}${offset}`;
}

function parseMoveOffer(value: unknown, date: string): MoveOffer {
  const offer = object(value, ['offer_id', 'date', 'timezone', 'expires_at', 'options']);
  if (offer.date !== date || !Array.isArray(offer.options)) return invalid();
  if (offer.options.length === 0) {
    if (offer.offer_id !== null || offer.expires_at !== null) return invalid();
    return offer as MoveOffer;
  }
  if (!uuid(offer.offer_id) || !instant(offer.expires_at) || typeof offer.timezone !== 'string') return invalid();
  let format: Intl.DateTimeFormat;
  try {
    format = new Intl.DateTimeFormat('en-CA', {timeZone: offer.timezone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZoneName: 'longOffset'});
  } catch { return invalid(); }
  const options = offer.options.map(value => {
    const option = object(value, ['option_id', ...timestamps]);
    if (!uuid(option.option_id)) return invalid();
    const local = {
      option_id: option.option_id,
      visit_start: zonedInstant(option.visit_start, format), visit_end: zonedInstant(option.visit_end, format),
      busy_start: zonedInstant(option.busy_start, format), busy_end: zonedInstant(option.busy_end, format),
    };
    checkWindow(local, date);
    return local;
  });
  return {...offer, options} as MoveOffer;
}

export function entryId(entry: CalendarEntry): string {
  switch (entry.kind) {
    case 'BLOCK': return entry.block_id;
    case 'APPOINTMENT': return entry.booking.appointment_id;
    case 'HOLD': return entry.booking.hold_id;
  }
}

export function workScope(scope: BusinessScope, {selection}: WorkEntry): SchedulingScope {
  return {...scope, client: selection.client_id, conversation: selection.conversation_id, request: selection.request_id,
    quote: selection.quote_id, order: selection.order_id, session: selection.session_id};
}

const command = (body: unknown, key: string, csrf: string): RequestInit => ({
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'Idempotency-Key': key, 'X-CSRF-Token': csrf},
  body: JSON.stringify(body),
});

export const ownerCalendarApi = {
  async day({workspace, business}: BusinessScope, date: string | undefined, signal: AbortSignal) {
    const query = date ? `?date=${encodeURIComponent(date)}` : '';
    return parseOwnerDay(await schedulingRequest(`${businessPath(workspace, business)}/scheduling/day${query}`, signal), date);
  },
  async moveOffer(scope: SchedulingScope, appointment: string, date: string, key: string, csrf: string, signal: AbortSignal) {
    const path = `${sessionPath(scope)}/booking/${encodeURIComponent(appointment)}/reschedule-offers`;
    return parseMoveOffer(await schedulingRequest(path, signal, command({...sessionReferences(scope), date}, key, csrf)), date);
  },
  async changeAppointment(scope: SchedulingScope, appointment: string, change: {reason: string; option_id?: string}, key: string, csrf: string, signal: AbortSignal) {
    const action = change.option_id === undefined ? 'cancel' : 'reschedule';
    const path = `${sessionPath(scope)}/booking/${encodeURIComponent(appointment)}/${action}`;
    const response = object(await schedulingRequest(path, signal, command({...sessionReferences(scope), ...change}, key, csrf)),
      ['outcome', 'session_id', 'booking']);
    const booking = parseBooking(response.booking);
    if (response.session_id !== scope.session || (action === 'cancel'
      ? response.outcome !== 'CANCELLED' || booking.outcome !== 'CANCELLED' || booking.appointment_id !== appointment
      : !['RESCHEDULED', 'UNCHANGED'].includes(String(response.outcome)) || booking.outcome !== 'CONFIRMED' ||
        (response.outcome === 'UNCHANGED' ? booking.appointment_id !== appointment : booking.previous_appointment_id !== appointment))) return invalid();
    return booking;
  },
  async changeBlock({workspace, business}: BusinessScope, selection: {start: string; end: string} | {release: string}, key: string, csrf: string, signal: AbortSignal) {
    const base = `${businessPath(workspace, business)}/scheduling/blocks`;
    const release = 'release' in selection ? selection.release : null;
    const path = release ? `${base}/${encodeURIComponent(release)}/release` : base;
    const block = object(await schedulingRequest(path, signal, command(release ? {} : selection, key, csrf)),
      ['block_id', 'outcome', 'start', 'end']);
    if (!uuid(block.block_id) || !instant(block.start) || !instant(block.end) ||
        block.outcome !== (release ? 'RELEASED' : 'BLOCKED') || (release && block.block_id !== release)) return invalid();
  },
};

export async function conflictMessage(scope: BusinessScope, affected: AffectedAllocation[], dates: string[], signal: AbortSignal) {
  const views = await Promise.all([...new Set(dates)].map(date => ownerCalendarApi.day(scope, date, signal).catch(() => null)));
  const entries = views.flatMap(view => view?.entries ?? []);
  const description = affected.map(({kind, id}) => {
    const row = entries.find(entry => entry.kind === kind && entryId(entry) === id);
    const title = kind === 'BLOCK' ? 'Блок' : kind === 'HOLD' ? 'Удержание' : 'Запись';
    if (!row) return `${title} #${id.slice(0, 8)}`;
    return row.kind === 'BLOCK'
      ? `${title} ${row.start.slice(11, 16)}–${row.end.slice(11, 16)}`
      : `${title} «${row.work_label}»`;
  }).join(', ');
  return description ? `Конфликт календаря. Это время занимает ${description}.` : 'Конфликт календаря. Изменение не сохранено.';
}
