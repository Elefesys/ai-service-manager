import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, expect, it, vi} from 'vitest';
import {OwnerCalendar} from './OwnerCalendar';
import {OwnerAppointmentActions} from './OwnerCalendarActions';
import type {OwnerDay} from './owner-calendar-api';
import type {Booking, SchedulingScope} from './scheduling-api';

afterEach(() => vi.unstubAllGlobals());

const scope = {
  workspace: '10000000-0000-4000-8000-000000000001',
  business: '10000000-0000-4000-8000-000000000002',
};
const resource = '10000000-0000-4000-8000-000000000003';
const date = '2030-04-06';
const day: OwnerDay = {
  date, now: '2030-04-04T00:00:00Z', timezone: 'Asia/Novosibirsk', resource_id: resource, schedule_version: 1,
  working_intervals: [{start_minute: 540, end_minute: 720}], exception: null, entries: [], history: [],
};
const json = (body: unknown) => new Response(JSON.stringify(body), {status: 200});
const expired = () => {};

it('drops delayed reads after a date or business change and cancels the read on close', async () => {
  const pending: {signal: AbortSignal; reply: (response: Response) => void}[] = [];
  vi.stubGlobal('fetch', vi.fn((_path: string, input: RequestInit) => new Promise<Response>(reply => {
    pending.push({signal: input.signal!, reply});
  })));
  const user = userEvent.setup();
  const other = {...scope, business: '10000000-0000-4000-8000-000000000004'};
  const {rerender} = render(<OwnerCalendar scope={scope} csrf="synthetic" expired={expired}/>);
  await user.click(screen.getByRole('button', {name: 'Открыть календарь'}));
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.change(screen.getByLabelText('Дата календаря'), {target: {value: date}});
  await waitFor(() => expect(pending).toHaveLength(2));
  expect(pending[0].signal.aborted).toBe(true);
  await act(async () => {
    pending[1].reply(json(day));
    pending[0].reply(json({...day, date: '2030-04-04', working_intervals: []}));
  });
  expect(screen.getByText('Рабочие часы 09:00–12:00')).toBeVisible();
  expect(screen.queryByText('Выходной.')).toBeNull();

  await user.click(screen.getByRole('button', {name: 'Следующий день'}));
  await waitFor(() => expect(pending).toHaveLength(3));
  rerender(<OwnerCalendar scope={other} csrf="synthetic" expired={expired}/>);
  await waitFor(() => expect(pending).toHaveLength(4));
  expect(pending[2].signal.aborted).toBe(true);
  await user.click(screen.getByRole('button', {name: 'Закрыть календарь'}));
  expect(pending[3].signal.aborted).toBe(true);
  await act(async () => {
    pending[3].reply(json({...day, date: '2030-04-07'}));
    pending[2].reply(json({...day, date: '2030-04-07'}));
  });
  expect(screen.queryByLabelText('Дата календаря')).toBeNull();
  expect(pending).toHaveLength(4);
});

it('retries a lost response with the same appointment, payload and key', async () => {
  const id = (end: string) => `10000000-0000-4000-8000-00000000000${end}`;
  const sessionScope: SchedulingScope = {...scope, client: id('4'), conversation: id('5'), request: id('6'),
    quote: id('7'), order: id('8'), session: id('9')};
  const booking: Booking = {
    outcome: 'CONFIRMED', appointment_id: id('4'), hold_id: id('5'), reschedule_option_id: null, previous_appointment_id: null,
    cancelled_at: null, cancelled_by: null, cancel_reason: null,
    resource_id: resource, allocation_id: id('6'), date, timezone: 'Asia/Novosibirsk',
    visit_start: `${date}T10:00:00+07:00`, visit_end: `${date}T11:05:00+07:00`,
    busy_start: `${date}T09:50:00+07:00`, busy_end: `${date}T11:10:00+07:00`,
  };
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('lost response')).mockResolvedValueOnce(json({
    outcome: 'CANCELLED', session_id: sessionScope.session,
    booking: {...booking, outcome: 'CANCELLED', cancelled_at: `${date}T09:00:00+07:00`, cancelled_by: id('7'), cancel_reason: 'Клиент отменил'},
  }));
  vi.stubGlobal('fetch', fetch);
  const user = userEvent.setup();
  render(<OwnerAppointmentActions scope={sessionScope} booking={booking} date={date} csrf="synthetic" expired={expired} changed={() => {}}/>);
  await user.click(screen.getByRole('button', {name: 'Отменить визит'}));
  await user.type(screen.getByLabelText('Причина отмены'), 'Клиент отменил');
  await user.click(screen.getByRole('button', {name: 'Подтвердить отмену'}));
  await user.click(await screen.findByRole('button', {name: 'Повторить ту же команду'}));
  expect(await screen.findByText('Визит отменён.')).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
  const [[firstPath, firstInit], [retryPath, retryInit]] = fetch.mock.calls;
  expect(firstPath).toMatch(new RegExp(`/booking/${booking.appointment_id}/cancel$`));
  expect([retryPath, retryInit.body, retryInit.headers]).toEqual([firstPath, firstInit.body, firstInit.headers]);
  expect(firstInit.headers['Idempotency-Key']).toMatch(/^[a-f0-9-]{36}$/);
});
