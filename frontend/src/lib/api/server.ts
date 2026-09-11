import {
  LedgerApiError,
  ledgerRequest,
  type ApiResponseBody,
  type LedgerRequestOptions,
} from "./client";
import type { GeneratedOperationId } from "./operations.generated";

/**
 * Server-only data access for the dashboard.
 *
 * Screens never build a URL and never fetch from the browser: they name a
 * generated contract operation and receive either its documented `data`
 * payload or a contract error. The bearer token is read from the server
 * environment, so it is never inlined into a client bundle.
 */

/** The documented 200 `data` payload for an operation. */
export type ApiData<Id extends GeneratedOperationId> =
  ApiResponseBody<Id> extends { data: infer Data } ? Data : never;

export type Loaded<T> =
  | { readonly ok: true; readonly data: T }
  | { readonly ok: false; readonly error: LedgerApiError };

interface Envelope<T> {
  readonly data: T;
}

/**
 * A transport failure is not a contract error, but it is still surfaced through
 * the same error component so operators see a correlation id when one exists.
 * HTTP status `0` means "no response was received".
 */
export function transportError(operationId: string, cause: unknown): LedgerApiError {
  const detail = cause instanceof Error ? cause.message : String(cause);
  return new LedgerApiError(
    0,
    "unexpected_error",
    `Could not reach the LEDGER service (${operationId}): ${detail}`,
    null,
    undefined,
  );
}

export function asLedgerApiError(operationId: string, error: unknown): LedgerApiError {
  return error instanceof LedgerApiError ? error : transportError(operationId, error);
}

/** Load an operation's `data` payload, converting every failure into a value. */
export async function loadData<Id extends GeneratedOperationId>(
  operationId: Id,
  options?: LedgerRequestOptions<Id>,
): Promise<Loaded<ApiData<Id>>> {
  try {
    const response = await ledgerRequest(operationId, options);
    return { ok: true, data: (response.body as Envelope<ApiData<Id>>).data };
  } catch (error) {
    return { ok: false, error: asLedgerApiError(operationId, error) };
  }
}
