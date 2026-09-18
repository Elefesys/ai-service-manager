import { describe, expect, it, vi } from 'vitest';
import { requireSafeResult, safeDiagnostic } from '../e2e/safe-diagnostic';

describe('safe browser diagnostics', () => {
  it('preserves failure without exposing sensitive causes or writing output', async () => {
    const stdout = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const stderr = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const secrets = ['Cookie=fake-cookie', 'X-CSRF-Token=fake-csrf', 'password=fake-password'];

    const result = await safeDiagnostic('ROTATE_ROUTE_FETCH_FAILED', async () => {
      throw new Error(secrets.join(' '));
    });

    let diagnostic = '';
    try { requireSafeResult(result); } catch (error) { diagnostic = String(error); }
    expect(diagnostic).toContain('E2E_SAFE_FAILURE:ROTATE_ROUTE_FETCH_FAILED');
    for (const secret of secrets) expect(diagnostic).not.toContain(secret);
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).not.toHaveBeenCalled();
  });
});
