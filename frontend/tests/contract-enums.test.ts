import { describe, expect, it } from "vitest";

import { loadContract } from "../scripts/lib/contract.mjs";
import { BATCH_STATES, DISCREPANCY_STATES, OUTCOMES, RESOLUTION_TYPES } from "@/lib/contract/enums";
import {
  BATCH_STATE_TONE,
  DISCREPANCY_STATE_TONE,
  OUTCOME_TONE,
  OUTCOME_LABEL,
} from "@/lib/contract/status";

describe("UI enums are the contract's enums", () => {
  it("renders all seven outcomes with a tone and label", () => {
    expect(OUTCOMES).toHaveLength(7);
    for (const outcome of OUTCOMES) {
      expect(OUTCOME_TONE[outcome]).toBeTruthy();
      expect(OUTCOME_LABEL[outcome]).toBeTruthy();
    }
  });

  it("maps every batch and discrepancy state to a tone", async () => {
    const contract = await loadContract();
    expect(BATCH_STATES).toEqual(contract.components.schemas.Batch.properties.state.enum);
    expect(DISCREPANCY_STATES).toEqual(
      contract.components.schemas.Discrepancy.properties.state.enum,
    );
    for (const state of BATCH_STATES) expect(BATCH_STATE_TONE[state]).toBeTruthy();
    for (const state of DISCREPANCY_STATES) expect(DISCREPANCY_STATE_TONE[state]).toBeTruthy();
  });

  it("offers only the resolution types the contract accepts", async () => {
    const contract = await loadContract();
    expect(RESOLUTION_TYPES).toEqual(
      contract.components.schemas.Resolution.properties.resolution_type.enum,
    );
  });
});
