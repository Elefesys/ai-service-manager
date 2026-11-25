import {act, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {IntakeError} from './intake-api';
import {bookingView, confirmedBooking, heldBooking, schedulingScope as scope} from './intake-fixtures.test-helper';
import {schedulingApi} from './scheduling-api';
import type {SessionBookingView} from './scheduling-api';
import {SessionBooking} from './SessionBooking';

afterEach(() => vi.restoreAllMocks());

it.each([
  [null, 'Время визита ещё не назначено.'],
  [confirmedBooking, 'Запись подтверждена.'],
  [heldBooking, 'Время удержано до 2026-11-26 17:00:13 · UTC+07:00, запись не подтверждена.'],
  [{...heldBooking, outcome: 'EXPIRED'}, 'Срок удержания истёк.'],
  [{...heldBooking, outcome: 'RELEASED'}, 'Удержание снято.'],
] as const)('renders the owner booking outcome %s', async (booking, message) => {
  const read = vi.spyOn(schedulingApi, 'booking').mockResolvedValue(bookingView(scope, booking));
  render(<SessionBooking scope={scope} expired={vi.fn()}/>);
  const panel = screen.getByRole('region', {name: 'Запись сейчас'});
  await waitFor(() => expect(panel).toHaveTextContent(message));
  if (booking?.outcome === 'HELD' || booking?.outcome === 'CONFIRMED') {
    expect(panel).toHaveTextContent(booking.date);
    expect(screen.getByText(booking.timezone)).toBeVisible();
    expect(screen.getByText('10:15–11:20 · UTC+07:00')).toBeVisible();
    expect(screen.getByText('10:05–11:25 · UTC+07:00')).toBeVisible();
  } else {
    expect(screen.queryByText('10:15–11:20 · UTC+07:00')).not.toBeInTheDocument();
  }
  expect(read).toHaveBeenCalledExactlyOnceWith(scope, expect.any(AbortSignal));
});

it('drops the previous booking when the selected session changes and a fresh read fails', async () => {
  const second = {...scope, session: '018f0000-0000-7000-8000-000000000050'};
  let reject!: (error: unknown) => void;
  const read = vi.spyOn(schedulingApi, 'booking').mockResolvedValueOnce(bookingView(scope, confirmedBooking))
    .mockImplementationOnce(() => new Promise((_, failure) => {reject = failure;}));
  const expired = vi.fn();
  const panel = render(<SessionBooking scope={scope} expired={expired}/>);
  expect(await screen.findByText('Запись подтверждена.')).toBeVisible();
  panel.rerender(<SessionBooking scope={second} expired={expired}/>);
  expect(read.mock.calls[0][1].aborted).toBe(true);
  expect(screen.queryByText('Запись подтверждена.')).not.toBeInTheDocument();
  await act(async () => reject(new IntakeError(503, 'UNAVAILABLE')));
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось прочитать состояние записи.');
  expect(screen.queryByText('10:15–11:20 · UTC+07:00')).not.toBeInTheDocument();
  expect(expired).not.toHaveBeenCalled();
});

it('discards an aborted booking response after switching work', async () => {
  const second = {...scope, request: '018f0000-0000-7000-8000-000000000051'};
  let complete!: (view: SessionBookingView) => void;
  const read = vi.spyOn(schedulingApi, 'booking').mockImplementationOnce(() => new Promise(resolve => {complete = resolve;}))
    .mockResolvedValueOnce(bookingView(second));
  const expired = vi.fn();
  const panel = render(<SessionBooking scope={scope} expired={expired}/>);
  panel.rerender(<SessionBooking scope={second} expired={expired}/>);
  await act(async () => complete(bookingView(scope, confirmedBooking)));
  expect(await screen.findByText('Время визита ещё не назначено.')).toBeVisible();
  expect(screen.queryByText('Запись подтверждена.')).not.toBeInTheDocument();
  expect(read.mock.calls[0][1].aborted).toBe(true);
});
