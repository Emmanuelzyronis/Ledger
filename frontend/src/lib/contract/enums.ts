import { GENERATED_ENUMS } from "@/lib/api/operations.generated";
import type { components } from "@/lib/api/schema";

/**
 * Contract enumerations, generated from the OpenAPI artifact and re-typed
 * against its schemas. Nothing here is hand-written, so a contract change
 * either regenerates these values or fails the contract test.
 */
export const OUTCOMES =
  GENERATED_ENUMS.outcomes satisfies readonly (keyof components["schemas"]["OutcomeCounts"])[];
export const RECONCILIATION_STATES = GENERATED_ENUMS.reconciliationStates;
export const DISCREPANCY_STATES = GENERATED_ENUMS.discrepancyStates;
export const BATCH_STATES = GENERATED_ENUMS.batchStates;
export const RESOLUTION_TYPES = GENERATED_ENUMS.resolutionTypes;
export const ERROR_CODES = GENERATED_ENUMS.errorCodes;
export const HEALTH_STATUSES = GENERATED_ENUMS.healthStatuses;

export type Outcome = (typeof OUTCOMES)[number];
export type ReconciliationState = (typeof RECONCILIATION_STATES)[number];
export type DiscrepancyState = (typeof DISCREPANCY_STATES)[number];
export type BatchState = (typeof BATCH_STATES)[number];
export type ResolutionType = (typeof RESOLUTION_TYPES)[number];
export type ErrorCode = (typeof ERROR_CODES)[number];

// Compile-time exhaustiveness for the enums the contract models as closed
// unions: if the contract adds a member without a regenerated tuple, these
// fail to typecheck. OutcomeCounts is an open map (propertyNames enum), so its
// closed set is guarded by the regeneration test instead.
type ExpectNever<T extends never> = T;
export type _ReconciliationStateExhaustive = ExpectNever<
  Exclude<NonNullable<components["schemas"]["Reconciliation"]["state"]>, ReconciliationState>
>;
export type _DiscrepancyStateExhaustive = ExpectNever<
  Exclude<components["schemas"]["Discrepancy"]["state"], DiscrepancyState>
>;
export type _BatchStateExhaustive = ExpectNever<
  Exclude<components["schemas"]["Batch"]["state"], BatchState>
>;
export type _ResolutionTypeExhaustive = ExpectNever<
  Exclude<components["schemas"]["Resolution"]["resolution_type"], ResolutionType>
>;
