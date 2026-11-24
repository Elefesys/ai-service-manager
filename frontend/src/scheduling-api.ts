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

const reasons = ['NO_WORKING_HOURS', 'NO_ACTIVE_POLICY', 'DURATION_UNAVAILABLE', 'DATE_CLOSED', 'NO_WINDOWS'] as const;
const timestamps = ['visit_start', 'visit_end', 'busy_start', 'busy_end'] as const;
type Slot = Record<(typeof timestamps)[number], string>;
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

const invalid = (): never => {throw new IntakeError(502, 'INVALID_RESPONSE');};
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const object = (v: unknown, keys: readonly string[]) => {
  if (!record(v) || Object.keys(v).length !== keys.length || !keys.every(k => Object.hasOwn(v, k))) return invalid();
  return v;
};
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(v);
const integer = (v: unknown, min: number, max: number): v is number => typeof v === 'number' && Number.isInteger(v) && min <= v && v <= max;
function dateValue(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const parsed = new Date(`${v}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === v;
}
const instant = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));

function checkIntervals(value: unknown, week: boolean) {
  if (!Array.isArray(value)) return invalid();
  for (const entry of value) {
    const interval = object(entry, week ? ['weekday', 'start_minute', 'end_minute'] : ['start_minute', 'end_minute']);
    if ((week && !integer(interval.weekday, 0, 6)) || !integer(interval.start_minute, 0, 1439) ||
        !integer(interval.end_minute, 1, 1440) || interval.end_minute <= interval.start_minute) invalid();
  }
}

export function parseAvailability(value: unknown, scope: SchedulingScope, date?: string): Availability {
  const view = object(value, ['request_id', 'quote_id', 'order_id', 'session_id', 'resource_id', 'service_name',
    'occupied_minutes', 'duration_reference_id', 'deposit', 'date', 'timezone', 'week', 'policy', 'exception', 'reason', 'windows']);
  if (view.request_id !== scope.request || view.quote_id !== scope.quote || view.order_id !== scope.order || view.session_id !== scope.session ||
      (view.resource_id !== null && !uuid(view.resource_id)) || typeof view.service_name !== 'string' || !view.service_name.trim() ||
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
  for (const entry of view.windows) {
    const {visit_start, visit_end, busy_start, busy_end} = object(entry, timestamps);
    if (!instant(visit_start) || !instant(visit_end) || !instant(busy_start) || !instant(busy_end) ||
        visit_start.slice(0, 10) !== view.date || Date.parse(busy_start) > Date.parse(visit_start) ||
        Date.parse(visit_start) >= Date.parse(visit_end) || Date.parse(visit_end) > Date.parse(busy_end)) invalid();
  }
  return view as Availability;
}

async function request(scope: SchedulingScope, date: string | undefined, signal: AbortSignal, init?: RequestInit) {
  const query = new URLSearchParams({client_id: scope.client, quote_id: scope.quote, order_id: scope.order});
  if (date) query.set('date', date);
  const {workspace, business, conversation, request: work, session} = scope;
  const id = encodeURIComponent;
  const path = `/api/v1/workspaces/${id(workspace)}/businesses/${id(business)}/intake/conversations/${id(conversation)}/service-requests/${id(work)}/sessions/${id(session)}/availability`;
  const response = await fetch(`${path}?${query}`, {...init, credentials: 'include', cache: 'no-store', signal: AbortSignal.any([signal, AbortSignal.timeout(10000)])});
  if (response.status !== 200) throw new IntakeError(response.status, 'SCHEDULING_REQUEST_FAILED');
  let value: unknown;
  try {value = await response.json();} catch {return invalid();}
  return value;
}

export const schedulingApi = {
  async preview(scope: SchedulingScope, date: string | undefined, signal: AbortSignal) {
    return parseAvailability(await request(scope, date, signal), scope, date);
  },
  async change(scope: SchedulingScope, date: string, body: ScheduleChange, csrf: string, signal: AbortSignal) {
    const queryDate = body.action === 'exception' ? undefined : date;
    const value = await request(scope, queryDate, signal, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body),
    });
    return parseAvailability(value, scope, body.action === 'exception' ? body.date : date);
  },
};
