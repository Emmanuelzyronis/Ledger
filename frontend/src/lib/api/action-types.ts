import type { components } from "./schema";

type ApiErrorCode = components["schemas"]["ErrorDetail"]["code"];

/**
 * Result envelope shared by the dashboard's server actions.
 *
 * Server actions run in the service process, so they cannot hand a
 * `LedgerApiError` instance to a client component. They return this plain,
 * serializable shape instead; the client rebuilds the error for display.
 */

export type ActionResult<T> =
  | { readonly ok: true; readonly data: T; readonly correlationId: string | null }
  | {
      readonly ok: false;
      readonly code: ApiErrorCode | "unexpected_error";
      readonly message: string;
      readonly status: number;
      readonly correlationId: string | null;
    };
