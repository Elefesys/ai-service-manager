import {instant, integer, invalid, object, schedulingRequest, sessionPath, sessionReferences, uuid} from './scheduling-api';
import type {SchedulingScope} from './scheduling-api';

type Obligation = {
  id: string;
  status: 'UNPAID';
  quote_version: string;
  terms_sha256: string;
  deposit_terms_version: string;
  acceptance_id: string;
  currency: 'RUB';
  mode: 'FIXED_DEPOSIT' | 'PERCENT_DEPOSIT' | 'FULL_PREPAYMENT';
  amount_minor: number;
  percent: number | null;
  rounding_version: 'HALF_UP_V1' | null;
} & (
  | {price_minor: number; price_range: null}
  | {price_minor: null; price_range: {authority: 'PROVISIONAL'; lower_minor: number; upper_minor: number}}
);

export type HoldPayment = {
  hold_id: string;
  allocation_id: string;
  expires_at: string;
  hold_status: 'HELD' | 'EXPIRED' | 'RELEASED' | 'CONFIRMED';
  requires_prepayment: boolean;
  obligation: Obligation | null;
};

type Hold = {hold_id: string; allocation_id: string};
const validMoney = (value: unknown) => integer(value, 1, 100000000000);

export function parseHoldPayment(value: unknown, hold: Hold): HoldPayment {
  const view = object(value, ['hold_id', 'allocation_id', 'expires_at', 'hold_status', 'requires_prepayment', 'obligation']);
  if (view.hold_id !== hold.hold_id || view.allocation_id !== hold.allocation_id || !instant(view.expires_at) ||
      !['HELD', 'EXPIRED', 'RELEASED', 'CONFIRMED'].some(status => status === view.hold_status) ||
      typeof view.requires_prepayment !== 'boolean') return invalid();
  if (view.obligation === null) return view as HoldPayment;

  const payment = object(view.obligation, ['id', 'status', 'quote_version', 'terms_sha256', 'deposit_terms_version',
    'acceptance_id', 'currency', 'price_minor', 'price_range', 'mode', 'amount_minor', 'percent', 'rounding_version']);
  if (!view.requires_prepayment || !uuid(payment.id) || payment.status !== 'UNPAID' ||
      !uuid(payment.deposit_terms_version) || !uuid(payment.acceptance_id) ||
      typeof payment.quote_version !== 'string' || !/^[1-9]\d{0,18}$/.test(payment.quote_version) ||
      typeof payment.terms_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(payment.terms_sha256) ||
      payment.currency !== 'RUB' || !validMoney(payment.amount_minor) ||
      !['FIXED_DEPOSIT', 'PERCENT_DEPOSIT', 'FULL_PREPAYMENT'].some(mode => mode === payment.mode)) return invalid();
  if (payment.price_range === null) {
    if (!validMoney(payment.price_minor)) return invalid();
  } else {
    const range = object(payment.price_range, ['authority', 'lower_minor', 'upper_minor']);
    if (payment.mode !== 'FIXED_DEPOSIT' || payment.price_minor !== null || range.authority !== 'PROVISIONAL' ||
        !validMoney(range.lower_minor) || !validMoney(range.upper_minor) || range.lower_minor >= range.upper_minor) return invalid();
  }
  if (payment.mode === 'PERCENT_DEPOSIT') {
    if (!integer(payment.percent, 1, 100) ||
        (payment.rounding_version !== null && payment.rounding_version !== 'HALF_UP_V1')) return invalid();
  } else if (payment.percent !== null || payment.rounding_version !== null) return invalid();
  return view as HoldPayment;
}

export const clientPaymentsApi = {
  async read(scope: SchedulingScope, hold: Hold, signal: AbortSignal) {
    const query = new URLSearchParams({...sessionReferences(scope), hold_id: hold.hold_id});
    return parseHoldPayment(await schedulingRequest(`${sessionPath(scope)}/payment-obligation?${query}`, signal), hold);
  },
  async open(scope: SchedulingScope, hold: Hold, key: string, csrf: string, signal: AbortSignal) {
    const result = await schedulingRequest(`${sessionPath(scope)}/payment-obligation`, signal, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': key},
      body: JSON.stringify({...sessionReferences(scope), hold_id: hold.hold_id}),
    }, ['STALE_STATE', 'NEEDS_CLARIFICATION']);
    return parseHoldPayment(result, hold);
  },
};
