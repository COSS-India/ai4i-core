import {
  aggregateTasks,
  hasPopulatedQuotaUsage,
  isMultiTaskQuotaTenant,
  summaryFromDetail,
} from "../../src/utils/usageSpendHelpers";
import type { TenantUsageItem } from "../../src/types/usageSpend";

const multiTaskTenant: TenantUsageItem = {
  tenantId: "tenant-auto-a",
  tenantName: "Tenant Auto A",
  tier: "Standard",
  tierId: "tier-1",
  currency: "INR",
  spend: 2163.24,
  budget: { limit: 1_000_000, spent: 2163.24, remaining: 997_836.63, percentageUsed: 0.2 },
  usage: {
    taskTypeCount: 5,
    unit: "Units",
    quotaLimit: null,
    consumed: null,
    remaining: null,
    percentage: null,
  },
  tierBreakdown: [
    {
      tierId: "tier-1",
      tierName: "Standard",
      spend: 2163.24,
      taskTypes: [
        { taskType: "nmt", unit: "characters", quotaLimit: 100_000, consumed: 9500, remaining: 90_500, percentage: 44.1, spend: 954 },
        { taskType: "ner", unit: "characters", quotaLimit: 50_000, consumed: 6600, remaining: 43_400, percentage: 30.3, spend: 656 },
        { taskType: "ocr", unit: "images", quotaLimit: 500, consumed: 20, remaining: 480, percentage: 9.2, spend: 200 },
      ],
    },
  ],
};

const singleTaskTenant: TenantUsageItem = {
  ...multiTaskTenant,
  usage: {
    taskTypeCount: 1,
    unit: "characters",
    quotaLimit: 100_000,
    consumed: 9500,
    remaining: 90_500,
    percentage: 9.5,
  },
  tierBreakdown: [
    {
      tierId: "tier-1",
      tierName: "Standard",
      spend: 954,
      taskTypes: [
        { taskType: "nmt", unit: "characters", quotaLimit: 100_000, consumed: 9500, remaining: 90_500, percentage: 100, spend: 954 },
      ],
    },
  ],
};

describe("quota usage helpers", () => {
  it("treats multi-task flat usage as unpopulated (no cross-unit summary)", () => {
    expect(isMultiTaskQuotaTenant(multiTaskTenant.usage)).toBe(true);
    expect(hasPopulatedQuotaUsage(multiTaskTenant.usage)).toBe(false);
  });

  it("treats single-task flat usage as populated", () => {
    expect(isMultiTaskQuotaTenant(singleTaskTenant.usage)).toBe(false);
    expect(hasPopulatedQuotaUsage(singleTaskTenant.usage)).toBe(true);
  });

  it("derives per-task-type rows from tierBreakdown for multi-task tenants", () => {
    const tasks = aggregateTasks(multiTaskTenant.tierBreakdown);
    expect(tasks).toHaveLength(3);
    expect(tasks[0]).toMatchObject({ taskType: "nmt", consumed: 9500, unit: "characters" });
  });

  it("builds spend summary from tierBreakdown, not the null flat usage block", () => {
    const summary = summaryFromDetail(multiTaskTenant);
    expect(summary.spendByModelTaskType).toHaveLength(3);
    expect(summary.totalSpend).toBeCloseTo(1810, 0);
  });
});
