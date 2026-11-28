import {render, screen} from '@testing-library/react';
import {expect, test, vi} from 'vitest';
import {PaymentObligation} from './PaymentObligation';
import type {Booking, SchedulingScope} from './scheduling-api';

const id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const scope: SchedulingScope = {
  workspace: id(1), business: id(2), conversation: id(3), client: id(4),
  request: id(5), quote: id(6), order: id(7), session: id(8),
};
const hold = {
  hold_id: id(9), allocation_id: id(10), resource_id: id(11), outcome: 'HELD',
  date: '2026-11-29', timezone: 'Asia/Novosibirsk',
  expires_at: '2026-11-28T11:00:00Z', visit_start: '2026-11-29T03:00:00Z',
  visit_end: '2026-11-29T04:00:00Z', busy_start: '2026-11-29T03:00:00Z', busy_end: '2026-11-29T04:05:00Z',
} satisfies Extract<Booking, {expires_at: string}>;

test('shows the original 99 kopecks and the bank card minimum without issuing a link command', async () => {
  const fetch = vi.fn(async (url: string) => Response.json(
    url.includes('/payment-checkout?') ? {
      checkout: {
        id: id(12), obligation_id: id(13), hold_id: hold.hold_id, expires_at: hold.expires_at,
        status: 'BLOCKED', reason: 'CARD_MINIMUM', delivery: null,
      },
    } : {
      hold_id: hold.hold_id, allocation_id: hold.allocation_id, expires_at: hold.expires_at,
      hold_status: 'HELD', requires_prepayment: true,
      obligation: {
        id: id(13), status: 'UNPAID', quote_version: '1', terms_sha256: '1'.repeat(64),
        deposit_terms_version: id(14), acceptance_id: id(15), currency: 'RUB',
        price_minor: 400000, price_range: null, mode: 'FIXED_DEPOSIT', amount_minor: 99,
        percent: null, rounding_version: null,
      },
    },
  ));
  vi.stubGlobal('fetch', fetch);
  try {
    render(<PaymentObligation scope={scope} booking={hold} csrf="controlled" expired={vi.fn()} />);
    expect(await screen.findByText('Для оплаты банковской картой нужна сумма от 1 ₽.')).toBeVisible();
    expect(screen.getByTestId('payment-obligation')).toHaveTextContent('фиксированная предоплата 0,99 ₽');
    expect(fetch.mock.calls.map(([url]) => url.split('?')[0].split('/').at(-1)).sort())
      .toEqual(['payment-checkout', 'payment-obligation']);
    expect(screen.queryByRole('button', {name: /ссылк/i})).not.toBeInTheDocument();
  } finally {
    vi.unstubAllGlobals();
  }
});
