import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { App } from './App';

describe('M0 shell', () => {
  it('renders Business Console and confirmed dependency health', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', component: 'database' }) }));
    render(<App pathname="/" />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Business Console');
    expect(await screen.findByText('Проверка готовности пройдена')).toBeVisible();
  });
  it('renders the separate ops surface without privileged data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(<App pathname="/ops/" />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Platform Operations');
    expect(await screen.findByText('Сервис недоступен или не готов')).toBeVisible();
  });
  it('does not interpret a successful HTTP response with invalid content as ready', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'invented' }) }));
    render(<App />);
    expect(await screen.findByText('Сервис недоступен или не готов')).toBeVisible();
  });
});
