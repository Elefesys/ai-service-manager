import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BillingPanel } from './BillingPanel';
import { billingApi, BillingError } from './billing-api';
import { billing, receipt, session, ws } from './billing-fixtures.test-helper';

beforeEach(() => {
  vi.spyOn(billingApi, 'read').mockResolvedValue(billing());
  vi.spyOn(billingApi, 'audit').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(billingApi, 'save').mockResolvedValue(receipt());
});
afterEach(() => vi.restoreAllMocks());
const ready = () => waitFor(() => expect(screen.getByRole('button', { name: 'Сохранить контакт' })).toBeEnabled());
const submit = () => fireEvent.submit(screen.getByRole('button', { name: 'Сохранить контакт' }).closest('form')!);

describe('C0 stale draft recovery regression', () => {
  it.each([false, true])('retains the frozen draft after auth recovery, stale replay and read failure=%s', async readFails => {
    const recover = vi.fn(), expired = vi.fn();
    const props = { session: session(), workspace: ws, recover, expired };
    const v = render(<BillingPanel {...props} />);
    await ready();
    vi.mocked(billingApi.save).mockRejectedValueOnce(new TypeError('delivery unknown')).mockRejectedValueOnce(new BillingError(409, 'STALE_STATE'));
    fireEvent.change(screen.getByLabelText('Имя контакта'), { target: { value: '  Original recovered draft  ' } });
    await act(async () => { submit(); });
    await screen.findByText(/Результат сохранения неизвестен/);
    fireEvent.click(screen.getByRole('button', { name: 'Проверить сессию для повтора' }));
    expect(recover).toHaveBeenCalledTimes(1);
    v.rerender(<BillingPanel {...props} session={null} workspace="" />);
    vi.mocked(billingApi.read).mockResolvedValue(billing('Concurrent committed contact', '2'));
    v.rerender(<BillingPanel {...props} session={session('fresh-csrf')} />);
    const retry = await screen.findByRole('button', { name: 'Повторить исходное сохранение' });
    await waitFor(() => expect(retry).toBeEnabled());
    if (readFails) vi.mocked(billingApi.read).mockRejectedValueOnce(new BillingError(503, 'UNAVAILABLE'));
    fireEvent.click(retry);
    await screen.findByText(/Конфликт версии/);
    if (readFails) {
      await screen.findByText('Не удалось получить данные. Повторите чтение.');
      fireEvent.click(screen.getByRole('button', { name: 'Обновить подписку' }));
    }
    await ready();
    expect(screen.getByLabelText('Имя контакта')).toHaveValue('  Original recovered draft  ');
    expect(screen.getByTestId('current-contact')).toHaveTextContent('Concurrent committed contact');
    const original = vi.mocked(billingApi.save).mock.calls[0];
    expect(billingApi.save).toHaveBeenCalledTimes(2);
    expect(vi.mocked(billingApi.save).mock.calls[1].slice(0, 3)).toEqual(original.slice(0, 3));
    // A subsequent same-actor session check and GET must retain an edited stale draft.
    fireEvent.change(screen.getByLabelText('Имя контакта'), { target: { value: 'Reviewed stale draft' } });
    v.rerender(<BillingPanel {...props} session={null} workspace="" />);
    vi.mocked(billingApi.read).mockResolvedValue(billing('Later committed contact', '3'));
    v.rerender(<BillingPanel {...props} session={session('newer-csrf')} />);
    await ready();
    expect(screen.getByLabelText('Имя контакта')).toHaveValue('Reviewed stale draft');
    expect(billingApi.save).toHaveBeenCalledTimes(2);
    await act(async () => { submit(); });
    await ready();
    const next = vi.mocked(billingApi.save).mock.calls[2];
    expect(next[1]).toEqual({ expected_version: '3', contact_display_name: 'Reviewed stale draft' });
    expect(next[2]).not.toBe(original[2]);
    expect(screen.getByLabelText('Имя контакта')).toHaveValue('Later committed contact');
  });

  it.each(['actor', 'workspace'])('retains a stale draft over read retries without carrying it into another %s', async context => {
    const props = { session: session(), workspace: ws, recover: vi.fn(), expired: vi.fn() };
    const v = render(<BillingPanel {...props} />);
    await ready();
    vi.mocked(billingApi.save).mockRejectedValueOnce(new BillingError(409, 'STALE_STATE'));
    vi.mocked(billingApi.read).mockRejectedValueOnce(new BillingError(503, 'UNAVAILABLE')).mockResolvedValue(billing('Current contact', '2'));
    fireEvent.change(screen.getByLabelText('Имя контакта'), { target: { value: 'Private stale draft' } });
    await act(async () => { submit(); });
    await screen.findByText('Не удалось получить данные. Повторите чтение.');
    fireEvent.click(screen.getByRole('button', { name: 'Обновить подписку' }));
    await ready();
    expect(screen.getByLabelText('Имя контакта')).toHaveValue('Private stale draft');
    const nextSession = context === 'actor' ? { ...session(), user_account_id: 'different-actor' } : { ...session(), memberships: [{ ...session().memberships[0], workspace_id: 'other-workspace' }] };
    v.rerender(<BillingPanel {...props} session={nextSession} workspace={context === 'workspace' ? 'other-workspace' : ws} />);
    await ready();
    expect(screen.getByLabelText('Имя контакта')).toHaveValue('Current contact');
    v.rerender(<BillingPanel {...props} />);
    await ready();
    expect(screen.getByLabelText('Имя контакта')).toHaveValue('Current contact');
    expect(billingApi.save).toHaveBeenCalledTimes(1);
  });
});
