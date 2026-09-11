import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

/** Absolute path to the published OpenAPI artifact in the repository. */
export const CONTRACT_PATH = fileURLToPath(
  new URL("../../../docs/openapi/ledger.v1.json", import.meta.url),
);

const HTTP_METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"];

export async function loadContract() {
  return JSON.parse(await readFile(CONTRACT_PATH, "utf8"));
}

/** Resolve a local `$ref` such as `#/components/schemas/Report` against the document. */
function deref(contract, node) {
  if (!node || typeof node !== "object" || !node.$ref) return node;
  const ref = node.$ref;
  if (!ref.startsWith("#/")) throw new Error(`Unsupported external $ref: ${ref}`);
  return ref
    .slice(2)
    .split("/")
    .reduce((acc, key) => acc?.[key], contract);
}

function parametersOf(contract, operation) {
  return (operation.parameters ?? [])
    .map((parameter) => deref(contract, parameter))
    .filter(Boolean);
}

/** The lowest documented 2xx status, which is the contract's success response. */
function successStatus(operation) {
  const codes = Object.keys(operation.responses ?? {})
    .filter((code) => /^2\d\d$/.test(code))
    .map(Number)
    .sort((a, b) => a - b);
  return codes.length > 0 ? String(codes[0]) : null;
}

/**
 * Reduce the contract to the operation facts the client needs: identity,
 * method, path, parameter names, body presence, and success status. Derived
 * only from the artifact — never hand-maintained.
 */
export function extractOperations(contract) {
  const operations = [];
  for (const [path, pathItem] of Object.entries(contract.paths ?? {})) {
    for (const method of HTTP_METHODS) {
      const operation = pathItem[method];
      if (!operation) continue;
      const parameters = parametersOf(contract, operation);
      const requestBodySchema = operation.requestBody
        ? deref(contract, operation.requestBody)?.content?.["application/json"]?.schema
        : undefined;
      operations.push({
        operationId: operation.operationId,
        method,
        path,
        tag: operation.tags?.[0] ?? null,
        isPublic: Array.isArray(operation.security) && operation.security.length === 0,
        pathParams: parameters.filter((p) => p.in === "path").map((p) => String(p.name)),
        queryParams: parameters.filter((p) => p.in === "query").map((p) => String(p.name)),
        hasRequestBody: Boolean(operation.requestBody),
        bodySchemaRef: requestBodySchema?.$ref ?? null,
        successStatus: successStatus(operation),
      });
    }
  }
  operations.sort((a, b) =>
    a.path === b.path ? a.method.localeCompare(b.method) : a.path.localeCompare(b.path),
  );
  return operations;
}

/**
 * Enumerations that the UI must not re-invent. Each is read out of the
 * contract's own schema so labels and ordering cannot drift from the API.
 */
export function extractEnums(contract) {
  const schemas = contract.components?.schemas ?? {};
  const pick = (path) => {
    const value = path.reduce((acc, key) => acc?.[key], schemas);
    if (!Array.isArray(value)) throw new Error(`Contract enum not found: ${path.join(".")}`);
    return value.filter((entry) => typeof entry === "string");
  };
  return {
    outcomes: pick(["OutcomeCounts", "propertyNames", "enum"]),
    reconciliationStates: pick(["Reconciliation", "properties", "state", "enum"]),
    discrepancyStates: pick(["Discrepancy", "properties", "state", "enum"]),
    batchStates: pick(["Batch", "properties", "state", "enum"]),
    resolutionTypes: pick(["Resolution", "properties", "resolution_type", "enum"]),
    errorCodes: pick(["ErrorDetail", "properties", "code", "enum"]),
    healthStatuses: pick(["Health", "properties", "status", "enum"]),
  };
}

const BANNER = (contract) =>
  [
    "// GENERATED FILE - DO NOT EDIT BY HAND.",
    "// Source: docs/openapi/ledger.v1.json",
    `// Contract: ${contract.info?.title ?? "unknown"} ${contract.info?.version ?? "unknown"}`,
    "// Regenerate with: npm run generate:api",
    "",
  ].join("\n");

/** Generated types for every path, operation, and schema in the contract. */
export async function generateSchemaModule(contract, astToString, openapiTS) {
  const ast = await openapiTS(JSON.parse(JSON.stringify(contract)), { alphabetize: true });
  return `${BANNER(contract)}${astToString(ast)}`;
}

function literalList(values, indent = "  ") {
  return values.map((value) => `${indent}${JSON.stringify(value)},`).join("\n");
}

/** Generated operation index the client is keyed by. */
export function generateOperationsModule(contract) {
  const operations = extractOperations(contract);
  const enums = extractEnums(contract);

  for (const operation of operations) {
    if (!operation.operationId) {
      throw new Error(
        `Contract operation without operationId: ${operation.method} ${operation.path}`,
      );
    }
  }

  const indexEntries = operations
    .map(
      (operation) =>
        `  ${operation.operationId}: { path: ${JSON.stringify(operation.path)}; method: ${JSON.stringify(
          operation.method,
        )} };`,
    )
    .join("\n");

  const operationEntries = operations
    .map((operation) =>
      [
        `  ${operation.operationId}: {`,
        `    operationId: ${JSON.stringify(operation.operationId)},`,
        `    method: ${JSON.stringify(operation.method)},`,
        `    path: ${JSON.stringify(operation.path)},`,
        `    tag: ${JSON.stringify(operation.tag)},`,
        `    isPublic: ${operation.isPublic},`,
        `    pathParams: ${JSON.stringify(operation.pathParams)},`,
        `    queryParams: ${JSON.stringify(operation.queryParams)},`,
        `    hasRequestBody: ${operation.hasRequestBody},`,
        `    successStatus: ${JSON.stringify(operation.successStatus)},`,
        "  },",
      ].join("\n"),
    )
    .join("\n");

  const bodyEntries = operations
    .filter((operation) => operation.bodySchemaRef)
    .map((operation) => {
      const schemaName = operation.bodySchemaRef.split("/").pop();
      return `  ${operation.operationId}: components["schemas"][${JSON.stringify(schemaName)}];`;
    })
    .join("\n");

  const pathParamEntries = operations
    .filter((operation) => operation.pathParams.length > 0)
    .map(
      (operation) =>
        `  ${operation.operationId}: { ${operation.pathParams
          .map((name) => `${name}: string`)
          .join("; ")} };`,
    )
    .join("\n");

  const queryParamEntries = operations
    .filter((operation) => operation.queryParams.length > 0)
    .map(
      (operation) =>
        `  ${operation.operationId}: { ${operation.queryParams
          .map((name) => `${name}?: string`)
          .join("; ")} };`,
    )
    .join("\n");

  const enumBlocks = Object.entries(enums)
    .map(([name, values]) => `  ${name}: [\n${literalList(values, "    ")}\n  ],`)
    .join("\n");

  return `${BANNER(contract)}import type { components, paths } from "./schema";

export const CONTRACT_OPENAPI = ${JSON.stringify(contract.openapi)} as const;
export const CONTRACT_VERSION = ${JSON.stringify(contract.info?.version ?? null)} as const;
export const CONTRACT_TITLE = ${JSON.stringify(contract.info?.title ?? null)} as const;

/** Operation id -> the path/method pair it addresses. Generated from the artifact. */
export interface OperationIndex {
${indexEntries}
}

/** Path parameters, keyed by operation id. Operations with none are absent. */
export interface OperationPathParams {
${pathParamEntries}
}

/** Query parameters, keyed by operation id. Operations with none are absent. */
export interface OperationQueryParams {
${queryParamEntries}
}

/** Request body schema, keyed by operation id. Operations with none are absent. */
export interface OperationRequestBodies {
${bodyEntries}
}

export type GeneratedOperationId = keyof OperationIndex;
export type GeneratedOperation = (typeof GENERATED_OPERATIONS)[GeneratedOperationId];

/** The full operation registry. This is the client's only source of endpoints. */
export const GENERATED_OPERATIONS = {
${operationEntries}
} as const;

export const GENERATED_OPERATION_IDS = [
${literalList(
  operations.map((operation) => operation.operationId),
  "  ",
)}
] as const satisfies readonly GeneratedOperationId[];

/** Operations the contract declares as unauthenticated (empty security list). */
export const GENERATED_PUBLIC_OPERATION_IDS = [
${literalList(
  operations.filter((operation) => operation.isPublic).map((operation) => operation.operationId),
  "  ",
)}
] as const satisfies readonly GeneratedOperationId[];

/** Contract enumerations, verbatim and in contract order. */
export const GENERATED_ENUMS = {
${enumBlocks}
} as const;

export type GeneratedEnumName = keyof typeof GENERATED_ENUMS;

/** Type-level re-exports so consumers can reference contract shapes directly. */
export type { components, paths };
`;
}
