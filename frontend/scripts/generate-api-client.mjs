#!/usr/bin/env node
import { writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

import {
  CONTRACT_PATH,
  generateOperationsModule,
  generateSchemaModule,
  loadContract,
} from "./lib/contract.mjs";

const SCHEMA_OUTPUT = new URL("../src/lib/api/schema.ts", import.meta.url);
const OPERATIONS_OUTPUT = new URL("../src/lib/api/operations.generated.ts", import.meta.url);

const contract = await loadContract();
const schema = await generateSchemaModule(contract, astToString, openapiTS);
const operations = generateOperationsModule(contract);

await writeFile(SCHEMA_OUTPUT, schema, "utf8");
await writeFile(OPERATIONS_OUTPUT, operations, "utf8");

console.log(`contract:    ${CONTRACT_PATH}`);
console.log(
  `operations:  ${Object.keys(contract.paths).length} paths -> src/lib/api/operations.generated.ts`,
);
console.log(`schema:      src/lib/api/schema.ts`);
