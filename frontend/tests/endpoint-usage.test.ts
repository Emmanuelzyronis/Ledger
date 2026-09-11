import { describe, expect, it } from "vitest";

import { loadContract } from "../scripts/lib/contract.mjs";
import {
  GENERATED_OPERATIONS,
  GENERATED_OPERATION_IDS,
  type GeneratedOperationId,
} from "@/lib/api/operations.generated";

import { readSources } from "./support/read";

const V1_LITERAL = /["'`](\/v1[^"'`]*)["'`]/g;

function staticPart(literal: string): string {
  const queryIndex = literal.indexOf("?");
  const withoutQuery = queryIndex === -1 ? literal : literal.slice(0, queryIndex);
  const templateIndex = withoutQuery.indexOf("${");
  return templateIndex === -1 ? withoutQuery : withoutQuery.slice(0, templateIndex);
}

describe("no screen references an endpoint outside the contract", () => {
  it("uses only paths that appear in docs/openapi/ledger.v1.json", async () => {
    const contract = await loadContract();
    const contractPaths = Object.keys(contract.paths);
    const violations: string[] = [];

    for (const file of await readSources()) {
      for (const match of file.text.matchAll(V1_LITERAL)) {
        const literal = match[1] ?? "";
        const prefix = staticPart(literal);
        const known = contractPaths.some((path) => path === prefix || path.startsWith(prefix));
        if (!known) violations.push(`${file.path}: "${literal}"`);
      }
    }

    expect(violations).toEqual([]);
  });

  it("keeps the client's operation ids in sync with the generated registry", () => {
    for (const operationId of GENERATED_OPERATION_IDS) {
      const operation: { method: string; path: string } = GENERATED_OPERATIONS[operationId];
      expect(operation.path.startsWith("/v1/")).toBe(true);
      expect(operation.method).toBe(operation.method.toLowerCase());
    }
    const ids: readonly GeneratedOperationId[] = GENERATED_OPERATION_IDS;
    expect(new Set(ids).size).toBe(ids.length);
  });
});
