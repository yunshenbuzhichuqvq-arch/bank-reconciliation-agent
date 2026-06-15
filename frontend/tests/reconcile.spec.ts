import { afterEach, describe, expect, it, vi } from "vitest";

import { uploadReconciliation } from "../src/api/reconcile";

const apiUpload = vi.hoisted(() =>
  vi.fn(async (_url: string, _form: FormData) => ({ task_id: "TASK-1" })),
);

vi.mock("../src/api/client", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiUpload,
}));

function file(name: string) {
  return new File(["x"], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

describe("uploadReconciliation", () => {
  afterEach(() => {
    apiUpload.mockClear();
  });

  it("uses BANK_ENTERPRISE as the default scenario_type", async () => {
    await uploadReconciliation(file("bank.xlsx"), file("clear.xlsx"));

    const form = apiUpload.mock.calls[0][1] as FormData;
    expect(form.get("scenario_type")).toBe("BANK_ENTERPRISE");
  });

  it("appends the selected scenario_type", async () => {
    await uploadReconciliation(file("bank.xlsx"), file("clear.xlsx"), "BANK_CLEARING");

    const form = apiUpload.mock.calls[0][1] as FormData;
    expect(form.get("scenario_type")).toBe("BANK_CLEARING");
  });
});
