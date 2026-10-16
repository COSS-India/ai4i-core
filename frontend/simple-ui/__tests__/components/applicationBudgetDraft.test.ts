/// <reference types="jest" />

import { belowAllocatedToKeys } from "../../src/config/budgetMessages";
import {
  applyResolved,
  buildDraftFromApplication,
  evaluateRowError,
  isApplicationBudgetEditable,
  rowHasBudgetChange,
  type BulkBudgetDraft,
} from "../../src/components/profile/applicationBudgetDraft";
import type { Application, ApplicationStatus } from "../../src/types/application";

function application(status: ApplicationStatus): Application {
  return {
    application_id: "42",
    tenant_id: "t1",
    name: "Billing",
    description: "desc",
    domain: "finance",
    allocated_percentage: 20,
    allocated_budget: 200,
    consumed_percentage: 5,
    consumed_budget: 40,
    status,
    created_at: "2026-01-01",
  };
}

function row(overrides: Partial<BulkBudgetDraft> = {}): BulkBudgetDraft {
  return {
    application_id: "42",
    name: "Billing",
    status: "ACTIVE",
    allocated_amount: null,
    consumed_percentage: null,
    consumed_budget: null,
    remaining_budget: null,
    originalPct: 20,
    pctInput: "20",
    resolvedPct: 20,
    resolvedAmount: 200,
    keysLoading: false,
    keysLoaded: true,
    keys: [],
    keyPreviews: [],
    rowError: null,
    inputNotice: null,
    ...overrides,
  };
}

describe("buildDraftFromApplication", () => {
  it("copies identity and allocation and leaves usage-list amounts empty", () => {
    expect(buildDraftFromApplication(application("ACTIVE"))).toEqual({
      application_id: "42",
      name: "Billing",
      status: "ACTIVE",
      allocated_amount: null,
      consumed_percentage: 5,
      consumed_budget: 40,
      remaining_budget: null,
      originalPct: 20,
      pctInput: "20",
      resolvedPct: 20,
      resolvedAmount: 200,
      keysLoading: false,
      keysLoaded: false,
      keys: [],
      keyPreviews: [],
      rowError: null,
      inputNotice: null,
    });
  });

  it("keeps an active application editable", () => {
    const draft = buildDraftFromApplication(application("ACTIVE"));
    expect(draft.status).toBe("ACTIVE");
    expect(isApplicationBudgetEditable(draft.status)).toBe(true);
  });

  it("keeps an inactive application not editable", () => {
    const draft = buildDraftFromApplication(application("INACTIVE"));
    expect(draft.status).toBe("INACTIVE");
    expect(isApplicationBudgetEditable(draft.status)).toBe(false);
  });
});

describe("rowHasBudgetChange", () => {
  it("is false when the percentage is unchanged", () => {
    expect(rowHasBudgetChange(row({ originalPct: 20, resolvedPct: 20 }))).toBe(false);
  });

  it("is true when the percentage changes", () => {
    expect(rowHasBudgetChange(row({ originalPct: 20, resolvedPct: 30 }))).toBe(true);
  });

  it("ignores a difference within the epsilon and reports one past it", () => {
    expect(rowHasBudgetChange(row({ originalPct: 10, resolvedPct: 10 + 1e-6 }))).toBe(false);
    expect(rowHasBudgetChange(row({ originalPct: 10, resolvedPct: 10 + 2e-6 }))).toBe(true);
  });
});

describe("isApplicationBudgetEditable", () => {
  it("allows only active applications", () => {
    expect(isApplicationBudgetEditable("ACTIVE")).toBe(true);
    expect(isApplicationBudgetEditable("INACTIVE")).toBe(false);
  });
});

describe("evaluateRowError", () => {
  it("requires a percentage when the row already has one", () => {
    expect(
      evaluateRowError(row({ pctInput: "", originalPct: 20, resolvedPct: null }), 1000),
    ).toBe("Enter a valid allocation percentage.");
  });

  it("rejects a percentage below 0", () => {
    expect(evaluateRowError(row({ pctInput: "-1", resolvedPct: -1 }), 1000)).toBe(
      "Enter a percentage between 0 and 100.",
    );
  });

  it("rejects a percentage above 100", () => {
    expect(evaluateRowError(row({ pctInput: "101", resolvedPct: 101 }), 1000)).toBe(
      "Enter a percentage between 0 and 100.",
    );
  });

  it("rejects an allocation below the consumed percentage", () => {
    expect(
      evaluateRowError(
        row({
          pctInput: "10",
          resolvedPct: 10,
          resolvedAmount: 100,
          consumed_percentage: 20,
        }),
        1000,
      ),
    ).toBe("Allocation cannot be lower than 20% already consumed.");
  });

  it("rejects an allocation below the amount already given to API keys", () => {
    const draft = row({
      pctInput: "10",
      resolvedPct: 10,
      resolvedAmount: 100,
      consumed_budget: 0,
      keys: [
        {
          id: 1,
          key_name: "primary",
          allocated_percentage: 50,
          allocated_budget: 500,
          consumed_budget: 0,
          is_active: true,
        },
      ],
    });
    expect(evaluateRowError(draft, 10000)).toBe(
      belowAllocatedToKeys("Billing", 500, 5, [{ name: "primary", amount: 500 }], "INR"),
    );
  });

  it("allows a reduction inside the per-key drift tolerance and rejects one past it", () => {
    const keys = [
      {
        id: 1,
        key_name: "primary",
        allocated_percentage: 50,
        allocated_budget: 100,
        consumed_budget: 0,
        is_active: true,
      },
    ];
    const within = row({
      pctInput: "10",
      resolvedPct: 10,
      resolvedAmount: 99.99,
      consumed_budget: 0,
      keys,
    });
    const past = row({ ...within, resolvedAmount: 99.98 });
    expect(evaluateRowError(within, 1000)).toBeNull();
    expect(evaluateRowError(past, 1000)).toBe(
      belowAllocatedToKeys("Billing", 100, 10, [{ name: "primary", amount: 100 }], "INR"),
    );
  });

  it("rejects a positive amount when the institution budget is not set", () => {
    expect(
      evaluateRowError(
        row({ pctInput: "10", resolvedPct: 10, resolvedAmount: 10 }),
        0,
      ),
    ).toBe("Institution budget is not set.");
  });

  it("rejects an allocation below the consumed amount", () => {
    expect(
      evaluateRowError(
        row({
          pctInput: "40",
          resolvedPct: 40,
          resolvedAmount: 10,
          consumed_budget: 50,
        }),
        1000,
      ),
    ).toBe("Allocation cannot be lower than 50 already consumed.");
  });
});

describe("applyResolved", () => {
  it("resolves a numeric percentage against the institution budget", () => {
    const next = applyResolved(row(), 1000, "25");
    expect(next.pctInput).toBe("25");
    expect(next.resolvedPct).toBe(25);
    expect(next.resolvedAmount).toBe(250);
    expect(next.rowError).toBeNull();
    expect(next.inputNotice).toBeNull();
  });

  it("previews active keys and leaves inactive keys out of the preview", () => {
    const next = applyResolved(
      row({
        keys: [
          {
            id: 1,
            key_name: "primary",
            allocated_percentage: 50,
            allocated_budget: 100,
            consumed_budget: 10,
            is_active: true,
          },
          {
            id: 2,
            key_name: "retired",
            allocated_percentage: 20,
            allocated_budget: 80,
            consumed_budget: 0,
            is_active: false,
          },
        ],
      }),
      1000,
      "40",
    );
    expect(next.resolvedPct).toBe(40);
    expect(next.resolvedAmount).toBe(400);
    expect(next.keyPreviews).toEqual([
      {
        id: 1,
        key_name: "primary",
        allocated_percentage: 25,
        allocated_budget: 100,
        floorViolation: false,
      },
    ]);
    expect(next.keys).toHaveLength(2);
    expect(next.rowError).toBeNull();
    expect(next.inputNotice).toBeNull();
    expect(next.name).toBe("Billing");
    expect(next.application_id).toBe("42");
  });
});
