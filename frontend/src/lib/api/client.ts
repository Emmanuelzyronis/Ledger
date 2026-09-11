import {
  GENERATED_OPERATIONS,
  GENERATED_PUBLIC_OPERATION_IDS,
  type GeneratedOperationId,
  type OperationIndex,
  type OperationPathParams,
  type OperationQueryParams,
  type OperationRequestBodies,
} from "./operations.generated";
import type { components, paths } from "./schema";

export type ApiErrorBody = components["schemas"]["Error"];
export type ApiErrorCode = components["schemas"]["ErrorDetail"]["code"];

type OperationFor<Id extends GeneratedOperationId> =
  paths[OperationIndex[Id]["path"]][OperationIndex[Id]["method"]];

/** The documented 200 `application/json` body for an operation. */
export type ApiResponseBody<Id extends GeneratedOperationId> =
  OperationFor<Id> extends {
    responses: { 200: { content: { "application/json": infer Body } } };
  }
    ? Body
    : never;

type PathParamsFor<Id extends GeneratedOperationId> = Id extends keyof OperationPathParams
  ? OperationPathParams[Id]
  : never;

type QueryParamsFor<Id extends GeneratedOperationId> = Id extends keyof OperationQueryParams
  ? OperationQueryParams[Id]
  : never;

type RequestBodyFor<Id extends GeneratedOperationId> = Id extends keyof OperationRequestBodies
  ? OperationRequestBodies[Id]
  : never;

export interface LedgerRequestOptions<Id extends GeneratedOperationId> {
  /** Path parameters. Required (and only accepted) for operations that declare them. */
  params?: PathParamsFor<Id>;
  /** Query parameters. Only accepted for operations that declare them. */
  query?: QueryParamsFor<Id>;
  /** Request body. Only accepted for operations that declare one. */
  body?: RequestBodyFor<Id>;
  /** Optional client correlation id; the API echoes it in the response body. */
  correlationId?: string;
  signal?: AbortSignal;
}

export interface LedgerResponse<Id extends GeneratedOperationId> {
  readonly status: number;
  /** Correlation id from the response header, when present. */
  readonly correlationId: string | null;
  readonly body: ApiResponseBody<Id>;
}

/** A failed `/v1` call carrying the contract's error envelope. */
export class LedgerApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | "unexpected_error";
  readonly correlationId: string | null;
  readonly body: unknown;

  constructor(
    status: number,
    code: ApiErrorCode | "unexpected_error",
    message: string,
    correlationId: string | null,
    body: unknown,
  ) {
    super(message);
    this.name = "LedgerApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
    this.body = body;
  }
}

/** Configuration is read per call so a missing token fails closed, with the API's own 401. */
export function apiBaseUrl(): string {
  return (process.env.LEDGER_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/+$/, "");
}

export function isPublicOperation(operationId: GeneratedOperationId): boolean {
  return (GENERATED_PUBLIC_OPERATION_IDS as readonly string[]).includes(operationId);
}

export function operationUrl<Id extends GeneratedOperationId>(
  operationId: Id,
  options: LedgerRequestOptions<Id> = {},
): string {
  const operation = GENERATED_OPERATIONS[operationId];
  const params = (options.params ?? {}) as Record<string, string | undefined>;
  const path = operation.path.replace(/\{([^}]+)\}/g, (_match, name: string) => {
    const value = params[name];
    if (value === undefined || value === "") {
      throw new Error(`${operationId}: missing path parameter "${name}"`);
    }
    return encodeURIComponent(value);
  });
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries((options.query ?? {}) as Record<string, unknown>)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const search = query.toString();
  return `${apiBaseUrl()}${path}${search ? `?${search}` : ""}`;
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length === 0) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const detail = (value as { error?: unknown }).error;
  return (
    typeof detail === "object" &&
    detail !== null &&
    typeof (detail as { code?: unknown }).code === "string"
  );
}

/**
 * Call a `/v1` operation. The endpoint is resolved from the generated contract
 * index, so no caller ever supplies a path string.
 */
export async function ledgerRequest<Id extends GeneratedOperationId>(
  operationId: Id,
  options: LedgerRequestOptions<Id> = {},
): Promise<LedgerResponse<Id>> {
  const headers = new Headers({ accept: "application/json" });
  const token = process.env.LEDGER_API_TOKEN;
  if (token) headers.set("authorization", `Bearer ${token}`);
  const correlationId = options.correlationId ?? process.env.LEDGER_API_CORRELATION_ID;
  if (correlationId) headers.set("x-correlation-id", correlationId);
  if (options.body !== undefined) headers.set("content-type", "application/json");

  const response = await fetch(operationUrl(operationId, options), {
    method: GENERATED_OPERATIONS[operationId].method.toUpperCase(),
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    cache: "no-store",
  });

  const body = await parseJson(response);

  if (!response.ok) {
    if (isErrorBody(body)) {
      throw new LedgerApiError(
        response.status,
        body.error.code,
        body.error.message,
        body.correlation_id ?? null,
        body,
      );
    }
    throw new LedgerApiError(
      response.status,
      "unexpected_error",
      `LEDGER API returned ${response.status} without the documented error envelope.`,
      response.headers.get("x-correlation-id"),
      body,
    );
  }

  return {
    status: response.status,
    correlationId: response.headers.get("x-correlation-id"),
    body: body as ApiResponseBody<Id>,
  };
}
