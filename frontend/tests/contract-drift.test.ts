import { readFile } from "node:fs/promises";

import openapiTS, { astToString } from "openapi-typescript";
import { describe, expect, it } from "vitest";

import {
  CONTRACT_PATH,
  extractEnums,
  extractOperations,
  generateOperationsModule,
  generateSchemaModule,
  loadContract,
} from "../scripts/lib/contract.mjs";
import {
  GENERATED_ENUMS,
  GENERATED_OPERATION_IDS,
  GENERATED_OPERATIONS,
  GENERATED_PUBLIC_OPERATION_IDS,
} from "@/lib/api/operations.generated";

const committedSchemaUrl = new URL("../src/lib/api/schema.ts", import.meta.url);
const committedOperationsUrl = new URL("../src/lib/api/operations.generated.ts", import.meta.url);

describe("generated client matches the published contract", () => {
  it("regenerates byte-identical artifacts (drift guard)", async () => {
    const contract = await loadContract();
    const expectedSchema = await generateSchemaModule(contract, astToString, openapiTS);
    const expectedOperations = generateOperationsModule(contract);

    expect(await readFile(committedSchemaUrl, "utf8")).toBe(expectedSchema);
    expect(await readFile(committedOperationsUrl, "utf8")).toBe(expectedOperations);
  });

  it("exposes exactly the artifact's operations and paths", async () => {
    const contract = await loadContract();
    const expected = extractOperations(contract)
      .map((operation) => ({
        operationId: operation.operationId,
        method: operation.method,
        path: operation.path,
      }))
      .sort((a, b) => a.operationId.localeCompare(b.operationId));

    const actual = GENERATED_OPERATION_IDS.map((operationId) => ({
      operationId,
      method: GENERATED_OPERATIONS[operationId].method,
      path: GENERATED_OPERATIONS[operationId].path,
    })).sort((a, b) => a.operationId.localeCompare(b.operationId));

    expect(actual).toEqual(expected);
    expect(actual.length).toBe(extractOperations(contract).length);
    const artifactPaths = new Set(Object.keys(contract.paths));
    for (const operation of actual) expect(artifactPaths.has(operation.path)).toBe(true);
  });

  it("marks exactly the artifact's unauthenticated operations as public", async () => {
    const contract = await loadContract();
    const expectedPublic = extractOperations(contract)
      .filter((operation) => operation.isPublic)
      .map((operation) => operation.operationId)
      .sort();
    expect([...GENERATED_PUBLIC_OPERATION_IDS].sort()).toEqual(expectedPublic);
  });

  it("derives every enum from the artifact", async () => {
    const contract = await loadContract();
    expect(GENERATED_ENUMS).toEqual(extractEnums(contract));
    expect(GENERATED_ENUMS.outcomes).toEqual([
      "MATCHED",
      "MISMATCHED",
      "UNMATCHED_A",
      "UNMATCHED_B",
      "AMBIGUOUS",
      "DUPLICATE",
      "INVALID",
    ]);
  });

  it("points at the repository's published artifact", () => {
    expect(CONTRACT_PATH.endsWith("docs/openapi/ledger.v1.json")).toBe(true);
  });
});
