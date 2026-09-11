// GENERATED FILE - DO NOT EDIT BY HAND.
// Source: docs/openapi/ledger.v1.json
// Contract: LEDGER Reconciliation API 1.0.0
// Regenerate with: npm run generate:api
import type { components, paths } from "./schema";

export const CONTRACT_OPENAPI = "3.1.0" as const;
export const CONTRACT_VERSION = "1.0.0" as const;
export const CONTRACT_TITLE = "LEDGER Reconciliation API" as const;

/** Operation id -> the path/method pair it addresses. Generated from the artifact. */
export interface OperationIndex {
  getAuditTrail: { path: "/v1/audit/{entity_type}/{entity_id}"; method: "get" };
  createBatch: { path: "/v1/batches"; method: "post" };
  getBatch: { path: "/v1/batches/{batch_id}"; method: "get" };
  ingestRecord: { path: "/v1/batches/{batch_id}/records"; method: "post" };
  listDiscrepancies: { path: "/v1/discrepancies"; method: "get" };
  getDiscrepancy: { path: "/v1/discrepancies/{discrepancy_id}"; method: "get" };
  resolveDiscrepancy: { path: "/v1/discrepancies/{discrepancy_id}/resolve"; method: "post" };
  exportData: { path: "/v1/export"; method: "get" };
  getHealth: { path: "/v1/health"; method: "get" };
  getReadiness: { path: "/v1/ready"; method: "get" };
  listReconciliations: { path: "/v1/reconciliations"; method: "get" };
  getReconciliation: { path: "/v1/reconciliations/{reconciliation_id}"; method: "get" };
  getReport: { path: "/v1/reports"; method: "get" };
  registerSource: { path: "/v1/sources"; method: "post" };
}

/** Path parameters, keyed by operation id. Operations with none are absent. */
export interface OperationPathParams {
  getAuditTrail: { entity_type: string; entity_id: string };
  getBatch: { batch_id: string };
  ingestRecord: { batch_id: string };
  getDiscrepancy: { discrepancy_id: string };
  resolveDiscrepancy: { discrepancy_id: string };
  getReconciliation: { reconciliation_id: string };
}

/** Query parameters, keyed by operation id. Operations with none are absent. */
export interface OperationQueryParams {
  listDiscrepancies: { batch_id?: string };
  exportData: { batch_id?: string };
  listReconciliations: { batch_id?: string };
  getReport: { batch_id?: string };
}

/** Request body schema, keyed by operation id. Operations with none are absent. */
export interface OperationRequestBodies {
  createBatch: components["schemas"]["CreateBatchRequest"];
  ingestRecord: components["schemas"]["IngestRecordRequest"];
  resolveDiscrepancy: components["schemas"]["ResolveDiscrepancyRequest"];
  registerSource: components["schemas"]["RegisterSourceRequest"];
}

export type GeneratedOperationId = keyof OperationIndex;
export type GeneratedOperation = (typeof GENERATED_OPERATIONS)[GeneratedOperationId];

/** The full operation registry. This is the client's only source of endpoints. */
export const GENERATED_OPERATIONS = {
  getAuditTrail: {
    operationId: "getAuditTrail",
    method: "get",
    path: "/v1/audit/{entity_type}/{entity_id}",
    tag: "Reporting",
    isPublic: false,
    pathParams: ["entity_type","entity_id"],
    queryParams: [],
    hasRequestBody: false,
    successStatus: "200",
  },
  createBatch: {
    operationId: "createBatch",
    method: "post",
    path: "/v1/batches",
    tag: "Ingestion",
    isPublic: false,
    pathParams: [],
    queryParams: [],
    hasRequestBody: true,
    successStatus: "200",
  },
  getBatch: {
    operationId: "getBatch",
    method: "get",
    path: "/v1/batches/{batch_id}",
    tag: "Ingestion",
    isPublic: false,
    pathParams: ["batch_id"],
    queryParams: [],
    hasRequestBody: false,
    successStatus: "200",
  },
  ingestRecord: {
    operationId: "ingestRecord",
    method: "post",
    path: "/v1/batches/{batch_id}/records",
    tag: "Ingestion",
    isPublic: false,
    pathParams: ["batch_id"],
    queryParams: [],
    hasRequestBody: true,
    successStatus: "200",
  },
  listDiscrepancies: {
    operationId: "listDiscrepancies",
    method: "get",
    path: "/v1/discrepancies",
    tag: "Reporting",
    isPublic: false,
    pathParams: [],
    queryParams: ["batch_id"],
    hasRequestBody: false,
    successStatus: "200",
  },
  getDiscrepancy: {
    operationId: "getDiscrepancy",
    method: "get",
    path: "/v1/discrepancies/{discrepancy_id}",
    tag: "Reporting",
    isPublic: false,
    pathParams: ["discrepancy_id"],
    queryParams: [],
    hasRequestBody: false,
    successStatus: "200",
  },
  resolveDiscrepancy: {
    operationId: "resolveDiscrepancy",
    method: "post",
    path: "/v1/discrepancies/{discrepancy_id}/resolve",
    tag: "Resolution",
    isPublic: false,
    pathParams: ["discrepancy_id"],
    queryParams: [],
    hasRequestBody: true,
    successStatus: "200",
  },
  exportData: {
    operationId: "exportData",
    method: "get",
    path: "/v1/export",
    tag: "Reporting",
    isPublic: false,
    pathParams: [],
    queryParams: ["batch_id"],
    hasRequestBody: false,
    successStatus: "200",
  },
  getHealth: {
    operationId: "getHealth",
    method: "get",
    path: "/v1/health",
    tag: "System",
    isPublic: true,
    pathParams: [],
    queryParams: [],
    hasRequestBody: false,
    successStatus: "200",
  },
  getReadiness: {
    operationId: "getReadiness",
    method: "get",
    path: "/v1/ready",
    tag: "System",
    isPublic: true,
    pathParams: [],
    queryParams: [],
    hasRequestBody: false,
    successStatus: "200",
  },
  listReconciliations: {
    operationId: "listReconciliations",
    method: "get",
    path: "/v1/reconciliations",
    tag: "Reporting",
    isPublic: false,
    pathParams: [],
    queryParams: ["batch_id"],
    hasRequestBody: false,
    successStatus: "200",
  },
  getReconciliation: {
    operationId: "getReconciliation",
    method: "get",
    path: "/v1/reconciliations/{reconciliation_id}",
    tag: "Reporting",
    isPublic: false,
    pathParams: ["reconciliation_id"],
    queryParams: [],
    hasRequestBody: false,
    successStatus: "200",
  },
  getReport: {
    operationId: "getReport",
    method: "get",
    path: "/v1/reports",
    tag: "Reporting",
    isPublic: false,
    pathParams: [],
    queryParams: ["batch_id"],
    hasRequestBody: false,
    successStatus: "200",
  },
  registerSource: {
    operationId: "registerSource",
    method: "post",
    path: "/v1/sources",
    tag: "Ingestion",
    isPublic: false,
    pathParams: [],
    queryParams: [],
    hasRequestBody: true,
    successStatus: "200",
  },
} as const;

export const GENERATED_OPERATION_IDS = [
  "getAuditTrail",
  "createBatch",
  "getBatch",
  "ingestRecord",
  "listDiscrepancies",
  "getDiscrepancy",
  "resolveDiscrepancy",
  "exportData",
  "getHealth",
  "getReadiness",
  "listReconciliations",
  "getReconciliation",
  "getReport",
  "registerSource",
] as const satisfies readonly GeneratedOperationId[];

/** Operations the contract declares as unauthenticated (empty security list). */
export const GENERATED_PUBLIC_OPERATION_IDS = [
  "getHealth",
  "getReadiness",
] as const satisfies readonly GeneratedOperationId[];

/** Contract enumerations, verbatim and in contract order. */
export const GENERATED_ENUMS = {
  outcomes: [
    "MATCHED",
    "MISMATCHED",
    "UNMATCHED_A",
    "UNMATCHED_B",
    "AMBIGUOUS",
    "DUPLICATE",
    "INVALID",
  ],
  reconciliationStates: [
    "CREATED",
    "EVALUATING",
    "MATCHED",
    "MISMATCHED",
    "UNMATCHED_A",
    "UNMATCHED_B",
    "AMBIGUOUS",
    "DUPLICATE",
    "INVALID",
    "RESOLVED",
  ],
  discrepancyStates: [
    "OPEN",
    "DEFERRED",
    "RESOLVED",
    "REJECTED",
  ],
  batchStates: [
    "RECEIVED",
    "VALIDATING",
    "VALIDATED",
    "REJECTED",
    "PROCESSING",
    "COMPLETED",
    "PARTIAL",
    "FAILED",
  ],
  resolutionTypes: [
    "AUTOMATIC",
    "MANUAL_APPROVED",
    "REJECTED",
    "DEFERRED",
  ],
  errorCodes: [
    "authentication_required",
    "invalid_token",
    "forbidden",
    "origin_not_allowed",
    "tls_required",
    "rate_limited",
    "payload_too_deep",
    "payload_too_large",
    "unsupported_media_type",
    "invalid_json",
    "missing_field",
    "invalid_request",
    "not_found",
    "unsupported_api_version",
    "internal_error",
  ],
  healthStatuses: [
    "ok",
    "degraded",
  ],
} as const;

export type GeneratedEnumName = keyof typeof GENERATED_ENUMS;

/** Type-level re-exports so consumers can reference contract shapes directly. */
export type { components, paths };
