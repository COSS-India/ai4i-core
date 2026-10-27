import {
  browserServiceListColumnStore,
  canToggleOffServiceListColumn,
  defaultServiceListColumnIds,
  loadServiceListColumns,
  parseServiceListColumnsPayload,
  parseServiceColumnPreferencePayload,
  parseVisibleColumnsPayload,
  resolveServiceListColumns,
  saveServiceListColumns,
  formatServiceListPrice,
  serviceListCellKey,
  serviceListColumnStorageKey,
  serviceListDateFilterInstant,
  serviceListFilterParams,
  servicePublishedOnMillis,
  toggleServiceListColumn,
  type ServiceListColumnDef,
  type ServiceListColumnId,
  type ServiceListColumnPreferenceStore,
} from "../../src/components/services-management/serviceListColumns";
import type { Service } from "../../src/types/platform";

const memoryStore = (): ServiceListColumnPreferenceStore & { data: Map<string, string[]> } => {
  const data = new Map<string, string[]>();
  return {
    data,
    read: (userId) => data.get(userId) ?? null,
    write: (userId, columnIds) => {
      data.set(userId, [...columnIds]);
    },
  };
};

describe("service list columns", () => {
  const defaults = defaultServiceListColumnIds();

  it("starts with the default set, including mandatory columns", () => {
    expect(defaults).toEqual([
      "name",
      "modelTaskType",
      "tier",
      "status",
      "createdAt",
      "actions",
    ]);
  });

  it("drops unknown ids and keeps catalogue order", () => {
    expect(
      resolveServiceListColumns(["publishedOn", "not-a-column", "name", "serviceId"]),
    ).toEqual(["name", "serviceId", "publishedOn", "actions"]);
  });

  it("restores defaults when only mandatory columns are stored", () => {
    expect(resolveServiceListColumns(["name", "actions"])).toEqual(defaults);
    expect(resolveServiceListColumns([])).toEqual(defaults);
    expect(resolveServiceListColumns(null)).toEqual(defaults);
  });

  it("refuses to hide the last column besides Name and Actions", () => {
    const onlyStatus: ServiceListColumnId[] = ["name", "status", "actions"];
    expect(canToggleOffServiceListColumn(onlyStatus, "status")).toBe(false);
    expect(toggleServiceListColumn(onlyStatus, "status")).toEqual(onlyStatus);
    expect(canToggleOffServiceListColumn(onlyStatus, "name")).toBe(false);
    expect(toggleServiceListColumn(onlyStatus, "name")).toEqual(onlyStatus);
  });

  it("adds and removes a column immediately, in catalogue order", () => {
    const next = toggleServiceListColumn(defaults, "serviceId");
    expect(next).toContain("serviceId");
    expect(next.indexOf("createdAt")).toBeLessThan(next.indexOf("serviceId"));
    expect(next.indexOf("serviceId")).toBeLessThan(next.indexOf("actions"));
    expect(toggleServiceListColumn(next, "serviceId")).toEqual(defaults);
  });

  it("stores a selection per user and leaves another user's selection alone", () => {
    const store = memoryStore();
    const saved = saveServiceListColumns("user-a", ["name", "modelName", "actions"], store);
    expect(saved).toEqual(["name", "modelName", "actions"]);
    expect(loadServiceListColumns("user-a", store)).toEqual(["name", "modelName", "actions"]);
    expect(loadServiceListColumns("user-b", store)).toEqual(defaults);
    expect(store.data.has("user-b")).toBe(false);
  });

  it("reset writes the default set for that user only", () => {
    const store = memoryStore();
    saveServiceListColumns("user-a", ["serviceId"], store);
    const reset = saveServiceListColumns("user-a", defaultServiceListColumnIds(), store);
    expect(reset).toEqual(defaults);
    expect(loadServiceListColumns("user-a", store)).toEqual(defaults);
  });

  it("accepts the columns API ids and drops ones that are not in that catalogue", () => {
    const catalogue: ServiceListColumnDef[] = [
      { id: "name", label: "Name", mandatory: true, defaultVisible: true },
      { id: "task_type", label: "Model Task Type", mandatory: false, defaultVisible: true },
      { id: "actions", label: "Actions", mandatory: true, defaultVisible: true },
    ];
    expect(resolveServiceListColumns(["model_name", "task_type"], catalogue)).toEqual([
      "name",
      "task_type",
      "actions",
    ]);
    expect(defaultServiceListColumnIds(catalogue)).toEqual(["name", "task_type", "actions"]);
  });

  it("parses the columns payload and builds filter query params", () => {
    const columns = parseServiceListColumnsPayload({
      success: true,
      data: {
        columns: [
          {
            id: "name",
            label: "Name",
            mandatory: true,
            defaultVisible: true,
            sortable: true,
            filterable: true,
            filter: { type: "text", params: ["name"], options: null },
          },
          {
            id: "task_type",
            label: "Model Task Type",
            mandatory: false,
            defaultVisible: true,
            sortable: true,
            filterable: true,
            filter: { type: "multi_select", params: ["task_types"], options: [] },
          },
          {
            id: "actions",
            label: "Actions",
            mandatory: true,
            defaultVisible: true,
            sortable: false,
            filterable: false,
            filter: null,
          },
        ],
      },
    });
    expect(columns?.map((column) => column.id)).toEqual(["name", "task_type", "actions"]);
    expect(
      serviceListFilterParams({
        columns: columns ?? [],
        filters: { name: "asr", task_type: "" },
        enabledTaskTypes: "asr,nmt",
      }),
    ).toEqual({ name: "asr", task_types: "asr,nmt" });
    expect(
      serviceListFilterParams({
        columns: columns ?? [],
        filters: { name: "", task_type: "llm" },
        enabledTaskTypes: "asr,nmt",
      }),
    ).toEqual({ task_types: "llm" });
  });

  it("reads visibleColumns from the preference payload", () => {
    expect(
      parseVisibleColumnsPayload({ data: { visibleColumns: ["task_type", "tier"] } }),
    ).toEqual(["task_type", "tier"]);
    expect(parseVisibleColumnsPayload({ data: {} })).toBeNull();
    expect(
      parseServiceColumnPreferencePayload({
        success: true,
        data: {
          viewKey: "service-list",
          visibleColumns: ["name", "actions", "task_type", "status"],
          isDefault: true,
        },
      }),
    ).toEqual({
      viewKey: "service-list",
      visibleColumns: ["name", "actions", "task_type", "status"],
      isDefault: true,
    });
  });

  it("maps published_at to the Published On cell and reads publishedAt", () => {
    expect(serviceListCellKey("published_at")).toBe("publishedOn");
    expect(
      servicePublishedOnMillis({
        publishedAt: "2026-10-26T10:00:00.000Z",
      } as Service),
    ).toBe(Date.parse("2026-10-26T10:00:00.000Z"));
    expect(
      servicePublishedOnMillis({
        publishedOn: 1_729_936_800,
      } as Service),
    ).toBe(1_729_936_800_000);
  });

  it("keeps eight decimals for service prices", () => {
    expect(formatServiceListPrice(0.00000025)).toContain("0.00000025");
  });

  it("maps date_range filters to local-offset ISO bounds", () => {
    const columns: ServiceListColumnDef[] = [
      {
        id: "created_at",
        label: "Created At",
        mandatory: false,
        defaultVisible: true,
        filterable: true,
        filter: {
          type: "date_range",
          params: ["created_from", "created_to"],
          options: null,
        },
      },
    ];
    const fromIso = serviceListDateFilterInstant("2026-10-01", "from");
    const toIso = serviceListDateFilterInstant("2026-10-26", "to");
    expect(fromIso).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00[+-]\d{2}:\d{2}$/);
    expect(toIso).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00[+-]\d{2}:\d{2}$/);
    expect(
      serviceListFilterParams({
        columns,
        filters: {
          created_at__from: "2026-10-01",
          created_at__to: "2026-10-26",
        },
        sortBy: "created_at",
        sortOrder: "desc",
      }),
    ).toEqual({
      created_from: fromIso,
      created_to: toIso,
      sort_by: "created_at",
      sort_order: "desc",
    });
  });

  it("normalizes multi_select values as comma-separated option ids", () => {
    const columns: ServiceListColumnDef[] = [
      {
        id: "tier",
        label: "Tier",
        mandatory: false,
        defaultVisible: true,
        filterable: true,
        filter: {
          type: "multi_select",
          params: ["tier_ids"],
          options: null,
        },
      },
    ];
    expect(
      serviceListFilterParams({
        columns,
        filters: { tier: " id-a , id-b " },
      }),
    ).toEqual({ tier_ids: "id-a,id-b" });
  });

  it("keys browser storage by user id", () => {
    const key = serviceListColumnStorageKey("user-a");
    window.localStorage.removeItem(key);
    window.localStorage.removeItem(serviceListColumnStorageKey("user-b"));
    browserServiceListColumnStore.write("user-a", ["name", "tier", "actions"]);
    expect(browserServiceListColumnStore.read("user-b")).toBeNull();
    expect(loadServiceListColumns("user-a")).toEqual(["name", "tier", "actions"]);
    window.localStorage.removeItem(key);
  });
});
