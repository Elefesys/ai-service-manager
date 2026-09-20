export type SafeResult<T> = { ok: true; value: T } | { ok: false; code: string };
export type SafeDiagnosticCode =
  | 'ROTATE_ROUTE_FETCH_FAILED'
  | 'ROTATE_ROUTE_ABORT_AFTER_FETCH_FAILURE'
  | 'ROTATE_ROUTE_ABORT_FAILED'
  | 'BILLING_HTTP_FAILED'
  | 'BILLING_BODY_FAILED'
  | 'BILLING_FIXTURE_FAILED'
  | 'BILLING_ROUTE_FETCH_FAILED'
  | 'BILLING_ROUTE_ABORT_FAILED'
  | 'BILLING_ROUTE_CONTINUE_FAILED';

export async function safeDiagnostic<T>(code: SafeDiagnosticCode, operation: () => Promise<T>): Promise<SafeResult<T>> {
  try {
    return { ok: true, value: await operation() };
  } catch {
    return { ok: false, code };
  }
}

export function requireSafeResult<T>(result: SafeResult<T>): T {
  if (!result.ok) throw new Error(`E2E_SAFE_FAILURE:${result.code}`);
  return result.value;
}
