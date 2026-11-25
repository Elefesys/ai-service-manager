import {IntakeError} from './intake-api';

export type SchedulingScope = {
  workspace: string;
  business: string;
  conversation: string;
  client: string;
  request: string;
  quote: string;
  order: string;
  session: string;
};

export type DayInterval = {start_minute: number; end_minute: number};
export type WeekInterval = DayInterval & {weekday: number};
export const policyLimits = {
  step_minutes: [1, 1440],
  buffer_before_minutes: [0, 1440],
  buffer_after_minutes: [0, 1440],
  minimum_notice_minutes: [0, 525600],
  horizon_days: [1, 365],
  offer_ttl_minutes: [1, 525600],
  hold_ttl_minutes: [1, 525600],
} as const;
export type PolicyField = keyof typeof policyLimits;
export type PolicySettings = Record<PolicyField, number>;
export const policyFields = Object.keys(policyLimits) as PolicyField[];
export type ScheduleChange =
  | {action: 'schedule'; timezone: string; week: WeekInterval[]}
  | ({action: 'policy'} & PolicySettings)
  | {action: 'exception'; date: string; windows: DayInterval[] | null};
export type ScheduleCommand = ScheduleChange & {expected_version: number};

const reasons = ['NO_WORKING_HOURS', 'NO_ACTIVE_POLICY', 'DURATION_UNAVAILABLE', 'DATE_CLOSED', 'NO_WINDOWS'] as const;
export const timestamps = ['visit_start', 'visit_end', 'busy_start', 'busy_end'] as const;
export type Slot = Record<(typeof timestamps)[number], string>;
type Deposit = {
  mode: 'NONE' | 'FIXED_DEPOSIT' | 'PERCENT_DEPOSIT' | 'FULL_PREPAYMENT';
  amount_minor: number | null;
  percent: number | null;
};
export type Availability = {
  request_id: string;
  quote_id: string;
  order_id: string;
  session_id: string;
  resource_id: string | null;
  schedule_version: number;
  service_name: string;
  occupied_minutes: number | null;
  duration_reference_id: string | null;
  deposit: Deposit;
  date: string;
  timezone: string | null;
  week: WeekInterval[];
  policy: (PolicySettings & {policy_id: string}) | null;
  exception: {date: string; windows: DayInterval[]} | null;
  reason: (typeof reasons)[number] | null;
  windows: Slot[];
};

type BookingInterval = Slot & {
  allocation_id: string;
  resource_id: string;
  date: string;
  timezone: string;
};

type Appointment = BookingInterval & {
  appointment_id: string;
  hold_id: string | null;
  previous_appointment_id: string | null;
  reschedule_option_id: string | null;
};
export type CancelledAppointment = Appointment & {
  outcome: 'CANCELLED'; cancelled_at: string; cancelled_by: string; cancel_reason: string;
};
export type Booking = CancelledAppointment |
  (Appointment & {outcome: 'CONFIRMED'; cancelled_at: null; cancelled_by: null; cancel_reason: null}) |
  (BookingInterval & {outcome: 'HELD' | 'EXPIRED' | 'RELEASED'; hold_id: string; expires_at: string});

export type SessionBookingView = {
  request_id: string;
  quote_id: string;
  order_id: string;
  session_id: string;
  booking: Booking | null;
  history: CancelledAppointment[];
};

export const invalid = (): never => {throw new IntakeError(502, 'INVALID_RESPONSE');};
export const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
export const object = (v: unknown, keys: readonly string[]) => {
  if (!record(v) || Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v, k))) return invalid();
  return v;
};
export const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(v);
export const integer = (v: unknown, min: number, max: number): v is number => typeof v === 'number' && Number.isInteger(v) && min <= v && v <= max;
export function dateValue(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const parsed = new Date(`${v}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === v;
}
export const instant = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));

export function checkIntervals(value: unknown, week: boolean) {
  if (!Array.isArray(value)) return invalid();
  for (const entry of value) {
    const interval = object(entry, week ? ['weekday', 'start_minute', 'end_minute'] : ['start_minute', 'end_minute']);
    if ((week && !integer(interval.weekday, 0, 6)) || !integer(interval.start_minute, 0, 1439) ||
        !integer(interval.end_minute, 1, 1440) || interval.end_minute <= interval.start_minute) invalid();
  }
}

export function checkWindow({visit_start, visit_end, busy_start, busy_end}: Record<string, unknown>, date: string) {
  if (!instant(visit_start) || !instant(visit_end) || !instant(busy_start) || !instant(busy_end) ||
      visit_start.slice(0, 10) !== date || Date.parse(busy_start) > Date.parse(visit_start) ||
      Date.parse(visit_start) >= Date.parse(visit_end) || Date.parse(visit_end) > Date.parse(busy_end)) invalid();
}

export function parseAvailability(value: unknown, scope: SchedulingScope, date?: string): Availability {
  const view = object(value, ['request_id', 'quote_id', 'order_id', 'session_id', 'resource_id', 'schedule_version', 'service_name',
    'occupied_minutes', 'duration_reference_id', 'deposit', 'date', 'timezone', 'week', 'policy', 'exception', 'reason', 'windows']);
  if (view.request_id !== scope.request || view.quote_id !== scope.quote || view.order_id !== scope.order || view.session_id !== scope.session ||
      (view.resource_id !== null && !uuid(view.resource_id)) || typeof view.service_name !== 'string' || !view.service_name.trim() ||
      !integer(view.schedule_version, 0, Number.MAX_SAFE_INTEGER) || (view.resource_id === null) !== (view.schedule_version === 0) ||
      (view.occupied_minutes !== null && !integer(view.occupied_minutes, 1, 10080)) ||
      (view.duration_reference_id !== null && !uuid(view.duration_reference_id)) || !dateValue(view.date) || (date && view.date !== date) ||
      (view.timezone !== null && (typeof view.timezone !== 'string' || !view.timezone)) ||
      (view.reason !== null && !reasons.some(reason => reason === view.reason)) || !Array.isArray(view.windows)) return invalid();
  const deposit = object(view.deposit, ['mode', 'amount_minor', 'percent']);
  if (!['NONE', 'FIXED_DEPOSIT', 'PERCENT_DEPOSIT', 'FULL_PREPAYMENT'].some(mode => mode === deposit.mode) ||
      (deposit.amount_minor !== null && !integer(deposit.amount_minor, 1, 100000000000)) ||
      (deposit.percent !== null && !integer(deposit.percent, 1, 100))) invalid();
  checkIntervals(view.week, true);
  if (view.policy !== null) {
    const policy = object(view.policy, ['policy_id', ...policyFields]);
    if (!uuid(policy.policy_id) || !policyFields.every(field => integer(policy[field], policyLimits[field][0], policyLimits[field][1]))) invalid();
  }
  if (view.exception !== null) {
    const exception = object(view.exception, ['date', 'windows']);
    if (exception.date !== view.date) invalid();
    checkIntervals(exception.windows, false);
  }
  if ((view.reason === null) !== (view.windows.length > 0)) invalid();
  for (const entry of view.windows) checkWindow(object(entry, timestamps), view.date);
  return view as Availability;
}

export function parseBooking(value: unknown): Booking {
  if (!record(value)) return invalid();
  const appointment = value.outcome === 'CONFIRMED' || value.outcome === 'CANCELLED';
  const appointmentFields = ['appointment_id', 'previous_appointment_id', 'reschedule_option_id',
    'cancelled_at', 'cancelled_by', 'cancel_reason'];
  const booking = object(value, ['outcome', 'hold_id', 'allocation_id', 'resource_id', 'date', 'timezone',
    ...timestamps, ...(appointment ? appointmentFields : ['expires_at'])]);
  if (!uuid(booking.allocation_id) || !uuid(booking.resource_id) || !dateValue(booking.date) ||
      typeof booking.timezone !== 'string' || !booking.timezone) return invalid();
  checkWindow(booking, booking.date);
  if (appointment) {
    const sourceValid = booking.hold_id === null
      ? uuid(booking.previous_appointment_id) && uuid(booking.reschedule_option_id)
      : uuid(booking.hold_id) && booking.previous_appointment_id === null && booking.reschedule_option_id === null;
    const cancellationValid = booking.outcome === 'CANCELLED'
      ? instant(booking.cancelled_at) && uuid(booking.cancelled_by) &&
        typeof booking.cancel_reason === 'string' && booking.cancel_reason.trim().length > 0
      : booking.cancelled_at === null && booking.cancelled_by === null && booking.cancel_reason === null;
    if (!uuid(booking.appointment_id) || !sourceValid || !cancellationValid) return invalid();
  } else if (!['HELD', 'EXPIRED', 'RELEASED'].some(outcome => outcome === booking.outcome) ||
      !uuid(booking.hold_id) || !instant(booking.expires_at)) {
    return invalid();
  }
  return booking as Booking;
}

export function parseSessionBooking(value: unknown, scope: SchedulingScope): SessionBookingView {
  const view = object(value, ['request_id', 'quote_id', 'order_id', 'session_id', 'booking', 'history']);
  if (view.request_id !== scope.request || view.quote_id !== scope.quote || view.order_id !== scope.order ||
      view.session_id !== scope.session || !Array.isArray(view.history)) return invalid();
  if (view.booking !== null) parseBooking(view.booking);
  for (const item of view.history) {
    if (parseBooking(item).outcome !== 'CANCELLED') return invalid();
  }
  return view as SessionBookingView;
}

export type AffectedAllocation = {kind: 'APPOINTMENT' | 'HOLD' | 'BLOCK'; id: string};

export class SchedulingError extends IntakeError {
  constructor(status: number, code: string, readonly affected: AffectedAllocation[] = []) {
    super(status, code);
  }
}

export const businessPath = (workspace: string, business: string) =>
  `/api/v1/workspaces/${encodeURIComponent(workspace)}/businesses/${encodeURIComponent(business)}`;

export function sessionPath(scope: SchedulingScope) {
  const {workspace, business, conversation, request: work, session} = scope;
  const id = encodeURIComponent;
  return `${businessPath(workspace, business)}/intake/conversations/${id(conversation)}/service-requests/${id(work)}/sessions/${id(session)}`;
}

export const sessionReferences = ({client, quote, order}: SchedulingScope) =>
  ({client_id: client, quote_id: quote, order_id: order});

export async function schedulingRequest(path: string, signal: AbortSignal, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, {
    ...init, credentials: 'include', cache: 'no-store',
    signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
  });
  const value: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = record(value) && record(value.error) ? value.error : null;
    const affected = error?.affected;
    const safe = Array.isArray(affected) ? affected.filter((item): item is AffectedAllocation =>
      record(item) && uuid(item.id) && (item.kind === 'BLOCK' || item.kind === 'APPOINTMENT' || item.kind === 'HOLD')) : [];
    const code = response.status === 409 && (error?.code === 'STALE_STATE' || error?.code === 'CALENDAR_CONFLICT')
      ? error.code : 'SCHEDULING_REQUEST_FAILED';
    throw new SchedulingError(response.status, code, safe);
  }
  if (response.status !== 200 || value === null) return invalid();
  return value;
}

async function request(scope: SchedulingScope, endpoint: 'availability' | 'booking', date: string | undefined, signal: AbortSignal, init?: RequestInit) {
  const query = new URLSearchParams(sessionReferences(scope));
  if (date) query.set('date', date);
  return schedulingRequest(`${sessionPath(scope)}/${endpoint}?${query}`, signal, init);
}

export const schedulingApi = {
  async booking(scope: SchedulingScope, signal: AbortSignal) {
    return parseSessionBooking(await request(scope, 'booking', undefined, signal), scope);
  },
  async preview(scope: SchedulingScope, date: string | undefined, signal: AbortSignal) {
    return parseAvailability(await request(scope, 'availability', date, signal), scope, date);
  },
  async change(scope: SchedulingScope, date: string, body: ScheduleCommand, csrf: string, signal: AbortSignal) {
    const queryDate = body.action === 'exception' ? undefined : date;
    const value = await request(scope, 'availability', queryDate, signal, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body),
    });
    return parseAvailability(value, scope, body.action === 'exception' ? body.date : date);
  },
};
