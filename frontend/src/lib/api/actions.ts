"use server";

import { revalidatePath } from "next/cache";

import type { ActionResult } from "./action-types";
import { ledgerRequest, type LedgerRequestOptions } from "./client";
import type { GeneratedOperationId } from "./operations.generated";
import type { components } from "./schema";
import { asLedgerApiError, type ApiData } from "./server";

type ResolutionType = components["schemas"]["ResolveDiscrepancyRequest"]["resolution_type"];

/**
 * Write operations, exposed as server actions so the bearer token stays in the
 * server process. Every action names a generated contract operation; none of
 * them constructs an endpoint or bypasses the domain authorization boundary.
 */

async function run<Id extends GeneratedOperationId>(
  operationId: Id,
  options?: LedgerRequestOptions<Id>,
): Promise<ActionResult<ApiData<Id>>> {
  try {
    const response = await ledgerRequest(operationId, options);
    return {
      ok: true,
      data: (response.body as { data: ApiData<Id> }).data,
      correlationId: response.correlationId,
    };
  } catch (error) {
    const apiError = asLedgerApiError(operationId, error);
    return {
      ok: false,
      code: apiError.code,
      message: apiError.message,
      status: apiError.status,
      correlationId: apiError.correlationId,
    };
  }
}

function text(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function list(formData: FormData, name: string): string[] {
  return text(formData, name)
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function jsonObject(value: string, label: string): Record<string, unknown> | string {
  if (value.length === 0) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return `${label} must be valid JSON.`;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return `${label} must be a JSON object.`;
  }
  return parsed as Record<string, unknown>;
}

function invalid(message: string): ActionResult<never> {
  return { ok: false, code: "invalid_request", message, status: 0, correlationId: null };
}

export async function registerSourceAction(
  _previous: ActionResult<ApiData<"registerSource">> | null,
  formData: FormData,
): Promise<ActionResult<ApiData<"registerSource">>> {
  const schemaVersions = list(formData, "schema_versions");
  if (schemaVersions.length === 0) {
    return invalid("At least one schema version is required.");
  }
  const result = await run("registerSource", {
    body: {
      source_id: text(formData, "source_id"),
      name: text(formData, "name"),
      schema_versions: schemaVersions,
      active: true,
    },
  });
  if (result.ok) revalidatePath("/ingest");
  return result;
}

export async function createBatchAction(
  _previous: ActionResult<ApiData<"createBatch">> | null,
  formData: FormData,
): Promise<ActionResult<ApiData<"createBatch">>> {
  const result = await run("createBatch", {
    body: {
      source_id: text(formData, "source_id"),
      external_batch_id: text(formData, "external_batch_id"),
      schema_version: text(formData, "schema_version"),
    },
  });
  if (result.ok) revalidatePath("/ingest");
  return result;
}

export async function ingestRecordAction(
  _previous: ActionResult<ApiData<"ingestRecord">> | null,
  formData: FormData,
): Promise<ActionResult<ApiData<"ingestRecord">>> {
  const batchId = text(formData, "batch_id");
  if (batchId.length === 0) return invalid("A batch id is required.");
  const payload = jsonObject(text(formData, "payload"), "Payload");
  if (typeof payload === "string") return invalid(payload);
  const idempotencyKey = text(formData, "idempotency_key");
  const result = await run("ingestRecord", {
    params: { batch_id: batchId },
    body: idempotencyKey.length > 0 ? { payload, idempotency_key: idempotencyKey } : { payload },
  });
  if (result.ok) {
    revalidatePath("/ingest");
    revalidatePath("/reconciliation");
  }
  return result;
}

export async function resolveDiscrepancyAction(
  _previous: ActionResult<ApiData<"resolveDiscrepancy">> | null,
  formData: FormData,
): Promise<ActionResult<ApiData<"resolveDiscrepancy">>> {
  const discrepancyId = text(formData, "discrepancy_id");
  if (discrepancyId.length === 0) return invalid("A discrepancy id is required.");
  const reason = text(formData, "reason");
  if (reason.length === 0) return invalid("A reason is required and is recorded immutably.");
  const evidence = jsonObject(text(formData, "evidence"), "Evidence");
  if (typeof evidence === "string") return invalid(evidence);
  const body: components["schemas"]["ResolveDiscrepancyRequest"] = {
    resolution_type: text(formData, "resolution_type") as ResolutionType,
    reason,
  };
  if (Object.keys(evidence).length > 0) body.evidence = evidence;
  const result = await run("resolveDiscrepancy", {
    params: { discrepancy_id: discrepancyId },
    body,
  });
  if (result.ok) {
    revalidatePath(`/discrepancies/${discrepancyId}`);
    revalidatePath("/discrepancies");
    revalidatePath("/reconciliation");
  }
  return result;
}
