// GENERATED FILE - DO NOT EDIT BY HAND.
// Source: docs/openapi/ledger.v1.json
// Contract: LEDGER Reconciliation API 1.0.0
// Regenerate with: npm run generate:api
export interface paths {
    "/v1/audit/{entity_type}/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get the append-only audit trail for an entity
         * @description Returns audit events ordered by `sequence`. Audit history is append-only and never mutated. `metadata` is the structured form of the stored audit metadata.
         */
        get: operations["getAuditTrail"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/batches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List batches visible to the caller
         * @description Lists batch metadata and counters for batches in the caller's source scope, ordered by `received_at` then `batch_id`. The optional `source_id` query narrows the list; a caller may not list a source outside its scope. Batches are read-only projections of authoritative batch state.
         */
        get: operations["listBatches"];
        put?: never;
        /**
         * Create an ingestion batch
         * @description Creates a batch for a source and schema version. A caller scoped to specific sources may only create batches for those sources. `(source_id, external_batch_id, schema_version)` is unique.
         */
        post: operations["createBatch"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/batches/{batch_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get batch state and counters
         * @description Returns the batch row plus its processing counters. A caller scoped to specific sources may only read batches belonging to those sources.
         */
        get: operations["getBatch"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/batches/{batch_id}/records": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ingest one raw record
         * @description Accepts one raw source record into a batch. Resubmitting identical content returns the original result with `duplicate_submission: true` instead of creating a new raw record, whether or not the idempotency key is reused; identical content targeted at a different batch links the same raw record to that batch. A syntactically valid but semantically invalid record is preserved as raw evidence and reported with `status: INVALID`.
         */
        post: operations["ingestRecord"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/discrepancies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List discrepancies
         * @description Lists discrepancies raised by ambiguous or unresolved reconciliation decisions. `state` is `OPEN` until a resolution is applied.
         */
        get: operations["listDiscrepancies"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/discrepancies/{discrepancy_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get one discrepancy */
        get: operations["getDiscrepancy"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/discrepancies/{discrepancy_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Apply an authorized resolution to a discrepancy
         * @description Records an immutable resolution and transitions the discrepancy. The discrepancy must be `OPEN`. Requires the `reconciliation_operator` role. Resolving a reconciliation discrepancy creates a new superseding reconciliation version; the superseded version remains retrievable, and a repeated resolution request returns the already-recorded resolution and never overwrites history.
         */
        post: operations["resolveDiscrepancy"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Redacted export projection
         * @description Returns the report, reconciliation rows, and discrepancy rows for the caller's scope, with raw payloads and sensitive-looking fields redacted to `[REDACTED]`. Read-only and never authoritative.
         */
        get: operations["exportData"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Liveness probe
         * @description Reports that the process is up. Exposes no business data and is exempt from TLS enforcement. Never requires authentication.
         */
        get: operations["getHealth"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Readiness probe
         * @description Reports whether the process can serve authoritative reads. Returns `503` with `data.status: degraded` when the database is unavailable. Exempt from TLS enforcement and never requires authentication.
         */
        get: operations["getReadiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reconciliations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List reconciliation decision rows
         * @description Lists every reconciliation version, including superseded versions preserved as historical evidence. Each row carries `outcome` (one of the seven reconciliation outcomes), `state`, `evidence`, and — for superseding versions — `supersedes_reconciliation_id`. Use `current_outcomes` from `GET /v1/reports` for the current view.
         */
        get: operations["listReconciliations"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reconciliations/{reconciliation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get one reconciliation decision row */
        get: operations["getReconciliation"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Reconciliation report
         * @description Returns reconciliation counts by outcome. `outcomes` counts every decision version; `current_outcomes` counts only current (non-superseded) versions. A caller scoped to specific sources may only filter by a batch belonging to those sources.
         */
        get: operations["getReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Register a data source
         * @description Registers or re-registers a source and the schema versions it may declare. Registration is idempotent for identical input.
         */
        post: operations["registerSource"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        AuditEvent: {
            actor: string;
            attempt_id: string | null;
            batch_id: string | null;
            causation_event_id: string | null;
            entity_id: string;
            entity_type: string;
            event_id: string;
            event_type: string;
            metadata: {
                [key: string]: unknown;
            };
            new_state: string | null;
            previous_state: string | null;
            reconciliation_id: string | null;
            record_id: string | null;
            sequence: number;
            stage_version: string;
            /** Format: date-time */
            timestamp: string;
        };
        AuditListResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["AuditEvent"][];
        };
        Batch: {
            batch_id: string;
            /** Format: date-time */
            completed_at: string | null;
            counters: components["schemas"]["BatchCounters"];
            error_summary: string | null;
            external_batch_id: string;
            /** Format: date-time */
            received_at: string;
            schema_version: string;
            source_id: string;
            /** Format: date-time */
            started_at: string | null;
            /** @enum {string} */
            state: "RECEIVED" | "VALIDATING" | "VALIDATED" | "REJECTED" | "PROCESSING" | "COMPLETED" | "PARTIAL" | "FAILED";
        };
        BatchCounters: {
            accepted_count: number;
            ambiguous_count: number;
            duplicate_count: number;
            failed_count: number;
            invalid_count: number;
            matched_count: number;
            mismatched_count: number;
            processed_count: number;
            received_count: number;
            rejected_input_count: number;
            unmatched_count: number;
        };
        BatchListResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Batch"][];
        };
        BatchResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Batch"];
        };
        /** @description Request correlation identifier. */
        CorrelationId: string;
        CreateBatchRequest: {
            external_batch_id: string;
            schema_version: string;
            source_id: string;
        };
        Discrepancy: {
            discrepancy_id: string;
            reason: string;
            reconciliation_id: string;
            /** @enum {string} */
            state: "OPEN" | "DEFERRED" | "RESOLVED" | "REJECTED";
        };
        DiscrepancyListResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Discrepancy"][];
        };
        DiscrepancyResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Discrepancy"];
        };
        Error: {
            correlation_id: components["schemas"]["CorrelationId"];
            error: components["schemas"]["ErrorDetail"];
        };
        ErrorDetail: {
            /**
             * @description Stable machine-readable error code.
             * @enum {string}
             */
            code: "authentication_required" | "invalid_token" | "forbidden" | "origin_not_allowed" | "tls_required" | "rate_limited" | "payload_too_deep" | "payload_too_large" | "unsupported_media_type" | "invalid_json" | "missing_field" | "invalid_request" | "not_found" | "unsupported_api_version" | "internal_error";
            /** @description Human-readable description; not stable. */
            message: string;
        };
        Export: {
            discrepancies: components["schemas"]["Discrepancy"][];
            reconciliations: components["schemas"]["Reconciliation"][];
            report: components["schemas"]["Report"];
        };
        ExportResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Export"];
        };
        Health: {
            /** @enum {string} */
            application: "ok";
            /** @enum {string} */
            database?: "ok" | "unavailable";
            /** @enum {string} */
            status: "ok" | "degraded";
        };
        HealthResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Health"];
        };
        IngestionResult: {
            batch_id: string;
            duplicate_submission: boolean;
            fingerprint: string | null;
            invalid_reason: string | null;
            raw_record_id: string | null;
            /** @enum {string} */
            status: "ACCEPTED" | "INVALID";
        };
        IngestionResultResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["IngestionResult"];
        };
        IngestRecordRequest: {
            /** @description Optional client key that makes a repeated submission of identical content return the original result. */
            idempotency_key?: string;
            /** @description Source-native record. Field names and required keys are defined by the batch's `schema_version`; the payload is preserved verbatim as raw evidence. */
            payload: {
                [key: string]: unknown;
            };
        };
        /** @description Counts keyed by reconciliation outcome. Absent outcomes are omitted rather than reported as zero. */
        OutcomeCounts: {
            [key: string]: number;
        };
        Reconciliation: {
            batch_id: string;
            evidence: {
                [key: string]: unknown;
            };
            /** @enum {string|null} */
            outcome: "MATCHED" | "MISMATCHED" | "UNMATCHED_A" | "UNMATCHED_B" | "AMBIGUOUS" | "DUPLICATE" | "INVALID" | null;
            raw_record_id: string | null;
            reconciliation_id: string;
            reconciliation_version: number;
            resolution_id: string | null;
            rule_version: string | null;
            source_a_record_id: string | null;
            source_b_record_id: string | null;
            /** @enum {string} */
            state: "CREATED" | "EVALUATING" | "MATCHED" | "MISMATCHED" | "UNMATCHED_A" | "UNMATCHED_B" | "AMBIGUOUS" | "DUPLICATE" | "INVALID" | "RESOLVED";
            supersedes_reconciliation_id: string | null;
        };
        ReconciliationListResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Reconciliation"][];
        };
        ReconciliationResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Reconciliation"];
        };
        RegisterSourceRequest: {
            /** @default true */
            active: boolean;
            name: string;
            schema_versions: string[];
            source_id: string;
        };
        Report: {
            batch_id: string | null;
            current_outcomes: components["schemas"]["OutcomeCounts"];
            current_reconciliation_count: number;
            discrepancy_count: number;
            outcomes: components["schemas"]["OutcomeCounts"];
            reconciliation_count: number;
            source_watermark: components["schemas"]["SourceWatermark"];
        };
        ReportResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Report"];
        };
        Resolution: {
            actor: string;
            /** Format: date-time */
            created_at: string;
            discrepancy_id: string;
            evidence: {
                [key: string]: unknown;
            };
            reason: string;
            reconciliation_id: string;
            resolution_id: string;
            /** @enum {string} */
            resolution_type: "AUTOMATIC" | "MANUAL_APPROVED" | "REJECTED" | "DEFERRED";
            rule_version: string | null;
        };
        ResolutionResult: {
            discrepancy: components["schemas"]["Discrepancy"];
            reconciliation: components["schemas"]["Reconciliation"];
            resolution: components["schemas"]["Resolution"];
        };
        ResolutionResultResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["ResolutionResult"];
        };
        ResolveDiscrepancyRequest: {
            /** @description Optional structured justification recorded immutably with the resolution. */
            evidence?: {
                [key: string]: unknown;
            };
            reason: string;
            /** @enum {string} */
            resolution_type: "AUTOMATIC" | "MANUAL_APPROVED" | "REJECTED" | "DEFERRED";
            rule_version?: string;
        };
        Source: {
            active: boolean;
            name: string;
            schema_versions: string[];
            source_id: string;
        };
        SourceResponse: {
            correlation_id: components["schemas"]["CorrelationId"];
            data: components["schemas"]["Source"];
        };
        SourceWatermark: {
            event_count: number;
            /** Format: date-time */
            timestamp: string | null;
        };
    };
    responses: {
        /** @description Malformed request: invalid JSON, a missing required field, an invalid field value, or a body exceeding the configured JSON depth limit. */
        BadRequest: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Authenticated but not permitted: insufficient role, source outside caller scope, or a disallowed request origin. */
        Forbidden: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Unexpected server-side failure. The message is intentionally generic; use `correlation_id` to find the request in logs. */
        InternalError: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description The endpoint, resource, or requested API version does not exist. */
        NotFound: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Request body exceeds the configured byte limit. */
        PayloadTooLarge: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Request rate limit exceeded. */
        RateLimited: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Missing or invalid bearer token. */
        Unauthorized: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description A request body was sent without `Content-Type: application/json`. */
        UnsupportedMediaType: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        /** @description Batch identifier returned by `POST /v1/batches`. */
        BatchId: string;
        /** @description Filter to one batch. The caller must be scoped to the batch's source. */
        BatchIdQuery: string;
        /** @description Client-supplied correlation identifier, echoed in the response body. */
        CorrelationId: string;
        /** @description Discrepancy identifier from `GET /v1/discrepancies`. */
        DiscrepancyId: string;
        /** @description Identifier of the audited entity. */
        EntityId: string;
        /** @description Audit entity type, for example `batch`, `record`, `reconciliation`, `discrepancy`, or `resolution`. */
        EntityType: string;
        /** @description Reconciliation decision identifier. */
        ReconciliationId: string;
        /** @description Filter to one source. The caller must be scoped to that source. */
        SourceIdQuery: string;
    };
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    getAuditTrail: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Identifier of the audited entity. */
                entity_id: components["parameters"]["EntityId"];
                /** @description Audit entity type, for example `batch`, `record`, `reconciliation`, `discrepancy`, or `resolution`. */
                entity_type: components["parameters"]["EntityType"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Audit events for the entity (empty when none exist). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": [],
                     *       "correlation_id": "b1c2d3e4-f506-4718-9a2b-c3d4e5f60718"
                     *     } */
                    "application/json": components["schemas"]["AuditListResponse"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    listBatches: {
        parameters: {
            query?: {
                /** @description Filter to one source. The caller must be scoped to that source. */
                source_id?: components["parameters"]["SourceIdQuery"];
            };
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Batch rows visible to the caller's scope. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": [],
                     *       "correlation_id": "0b7e5f0a-1a2b-4c3d-8e4f-5a6b7c8d9e0f"
                     *     } */
                    "application/json": components["schemas"]["BatchListResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    createBatch: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                /** @example {
                 *       "source_id": "source-a",
                 *       "external_batch_id": "2026-09-11-a",
                 *       "schema_version": "source_a.v1"
                 *     } */
                "application/json": components["schemas"]["CreateBatchRequest"];
            };
        };
        responses: {
            /** @description The created batch with zeroed counters. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            413: components["responses"]["PayloadTooLarge"];
            415: components["responses"]["UnsupportedMediaType"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    getBatch: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Batch identifier returned by `POST /v1/batches`. */
                batch_id: components["parameters"]["BatchId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The batch and its counters. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchResponse"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    ingestRecord: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Batch identifier returned by `POST /v1/batches`. */
                batch_id: components["parameters"]["BatchId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                /** @example {
                 *       "payload": {
                 *         "record_id": "A001",
                 *         "occurred_at": "2026-09-01",
                 *         "amount": "100.00",
                 *         "currency": "USD",
                 *         "direction": "CREDIT"
                 *       },
                 *       "idempotency_key": "batch-a:A001"
                 *     } */
                "application/json": components["schemas"]["IngestRecordRequest"];
            };
        };
        responses: {
            /** @description The ingestion result. `duplicate_submission` distinguishes a resubmission from a first acceptance. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": {
                     *         "batch_id": "batch-17296c52c3d444b081f99b4aa189bd8a",
                     *         "raw_record_id": "raw:source-a:source_a.v1:a01bb22d25d82ea63bb67529d4df8c97759e83467786abaa938fd7dcc8330985",
                     *         "status": "ACCEPTED",
                     *         "fingerprint": "a01bb22d25d82ea63bb67529d4df8c97759e83467786abaa938fd7dcc8330985",
                     *         "invalid_reason": null,
                     *         "duplicate_submission": false
                     *       },
                     *       "correlation_id": "8a1c3a5e-5b8d-4a5e-9a1f-3a8a0d0e6a11"
                     *     } */
                    "application/json": components["schemas"]["IngestionResultResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            413: components["responses"]["PayloadTooLarge"];
            415: components["responses"]["UnsupportedMediaType"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    listDiscrepancies: {
        parameters: {
            query?: {
                /** @description Filter to one batch. The caller must be scoped to the batch's source. */
                batch_id?: components["parameters"]["BatchIdQuery"];
            };
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Discrepancy rows visible to the caller's scope. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": [],
                     *       "correlation_id": "6f1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8"
                     *     } */
                    "application/json": components["schemas"]["DiscrepancyListResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    getDiscrepancy: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Discrepancy identifier from `GET /v1/discrepancies`. */
                discrepancy_id: components["parameters"]["DiscrepancyId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The discrepancy row. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DiscrepancyResponse"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    resolveDiscrepancy: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Discrepancy identifier from `GET /v1/discrepancies`. */
                discrepancy_id: components["parameters"]["DiscrepancyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                /** @example {
                 *       "resolution_type": "MANUAL_APPROVED",
                 *       "reason": "Verified against the September bank statement.",
                 *       "evidence": {
                 *         "reference": "stmt-2026-09"
                 *       }
                 *     } */
                "application/json": components["schemas"]["ResolveDiscrepancyRequest"];
            };
        };
        responses: {
            /** @description The recorded resolution together with the updated discrepancy and resulting reconciliation version. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResolutionResultResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            413: components["responses"]["PayloadTooLarge"];
            415: components["responses"]["UnsupportedMediaType"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    exportData: {
        parameters: {
            query?: {
                /** @description Filter to one batch. The caller must be scoped to the batch's source. */
                batch_id?: components["parameters"]["BatchIdQuery"];
            };
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Redacted export projection. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    getHealth: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The process is running. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": {
                     *         "status": "ok",
                     *         "application": "ok"
                     *       },
                     *       "correlation_id": "health"
                     *     } */
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    getReadiness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The database is reachable. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": {
                     *         "status": "ok",
                     *         "application": "ok",
                     *         "database": "ok"
                     *       },
                     *       "correlation_id": "ready"
                     *     } */
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description The database is unavailable; the body is still the health data shape. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": {
                     *         "status": "degraded",
                     *         "application": "ok",
                     *         "database": "unavailable"
                     *       },
                     *       "correlation_id": "ready"
                     *     } */
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    listReconciliations: {
        parameters: {
            query?: {
                /** @description Filter to one batch. The caller must be scoped to the batch's source. */
                batch_id?: components["parameters"]["BatchIdQuery"];
            };
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Reconciliation rows visible to the caller's scope. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": [],
                     *       "correlation_id": "0b7e5f0a-1a2b-4c3d-8e4f-5a6b7c8d9e0f"
                     *     } */
                    "application/json": components["schemas"]["ReconciliationListResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    getReconciliation: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Reconciliation decision identifier. */
                reconciliation_id: components["parameters"]["ReconciliationId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The reconciliation row. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconciliationResponse"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    getReport: {
        parameters: {
            query?: {
                /** @description Filter to one batch. The caller must be scoped to the batch's source. */
                batch_id?: components["parameters"]["BatchIdQuery"];
            };
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Derived report projection. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
    registerSource: {
        parameters: {
            query?: never;
            header?: {
                /** @description Client-supplied correlation identifier, echoed in the response body. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                /** @example {
                 *       "source_id": "source-a",
                 *       "name": "Source A",
                 *       "schema_versions": [
                 *         "source_a.v1"
                 *       ]
                 *     } */
                "application/json": components["schemas"]["RegisterSourceRequest"];
            };
        };
        responses: {
            /** @description The registered source. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /** @example {
                     *       "data": {
                     *         "source_id": "source-a",
                     *         "name": "Source A",
                     *         "schema_versions": [
                     *           "source_a.v1"
                     *         ],
                     *         "active": true
                     *       },
                     *       "correlation_id": "2b7c0f2e-2a4c-4d5a-9f2f-2b0f9c2b1f11"
                     *     } */
                    "application/json": components["schemas"]["SourceResponse"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            413: components["responses"]["PayloadTooLarge"];
            415: components["responses"]["UnsupportedMediaType"];
            429: components["responses"]["RateLimited"];
            500: components["responses"]["InternalError"];
        };
    };
}
