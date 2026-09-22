import { describe, expect, it, vi } from 'vitest';
import { requireSafeResult, safeDiagnostic } from '../e2e/safe-diagnostic';

describe('safe browser diagnostics', () => {
  it.each(['ROTATE_ROUTE_FETCH_FAILED', 'MESSAGING_HTTP_FAILED', 'MESSAGING_ROUTE_FETCH_FAILED', 'MESSAGING_FIXTURE_FAILED', 'MESSAGING_ROUTE_RELEASE_FAILED'] as const)('preserves %s without exposing sensitive causes or writing output', async code => {
    const stdout = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const stderr = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const secrets = ['Cookie=fake-cookie', 'X-CSRF-Token=fake-csrf', 'password=fake-password', 'text=private-message', 'Idempotency-Key=private-key', 'https://files.example/private?X-Amz-Signature=private'];

    const result = await safeDiagnostic(code, async () => {
      throw new Error(secrets.join(' '));
    });

    let diagnostic = '';
    try { requireSafeResult(result); } catch (error) { diagnostic = String(error); }
    expect(diagnostic).toContain(`E2E_SAFE_FAILURE:${code}`);
    for (const secret of secrets) expect(diagnostic).not.toContain(secret);
    expect(stdout).not.toHaveBeenCalled();
    expect(stderr).not.toHaveBeenCalled();
  });
});
