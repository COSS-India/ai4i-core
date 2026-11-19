import {
  SERVICE_LIST_COLUMNS,
  SERVICE_SORTABLE_COLUMN_IDS,
  browserServiceListColumnStore,
  canToggleOffServiceListColumn,
  defaultServiceListColumnIds,
  loadServiceListColumns,
  resolveServiceListColumns,
  saveServiceListColumns,
  formatServiceListPrice,
  serviceListCellKey,
  serviceListColumnsForRole,
  serviceListColumnsFromConfig,
  serviceListColumnStorageKey,
  serviceListDateFilterInstant,
  serviceListFilterParams,
  servicePublishedOnMillis,
  toggleServiceListColumn,
  type ServiceListColumnDef,
  type ServiceListColumnId,
  type ServiceListColumnPreferenceStore,
} from "../../src/components/services-management/serviceListColumns";
import { mandatoryColumnsHint } from "../../src/components/common/AdminListColumnPicker";
import { seesAdminServiceListColumns } from "../../src/utils/rbac";
import { parseServiceColumnConfig } from "../../src/services/configManagementService";
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

  it("starts with only the mandatory columns", () => {
    expect(defaults).toEqual(["name", "task_type", "model_name", "tier", "actions"]);
  });

  it("makes Name, Task Type, Model Name, Tier and Actions mandatory", () => {
    expect(
      SERVICE_LIST_COLUMNS.filter((column) => column.mandatory).map((column) => column.id),
    ).toEqual(["name", "task_type", "model_name", "tier", "actions"]);
  });

  it("sorts every column except Actions", () => {
    expect([...SERVICE_SORTABLE_COLUMN_IDS].sort()).toEqual(
      SERVICE_LIST_COLUMNS.map((column) => column.id)
        .filter((id) => id !== "actions")
        .sort(),
    );
  });

  it("carries the filter metadata GET /services needs", () => {
    const byId = new Map(SERVICE_LIST_COLUMNS.map((column) => [column.id, column]));
    expect(byId.get("task_type")?.filter?.params).toEqual(["task_types"]);
    expect(byId.get("status")?.filter).toEqual({
      type: "single_select",
      params: ["is_published"],
      options: [
        { value: "true", label: "Published" },
        { value: "false", label: "Unpublished" },
      ],
    });
    expect(byId.get("created_at")?.filter?.params).toEqual(["created_from", "created_to"]);
    expect(byId.get("input_price")?.filterable).toBeFalsy();
  });

  it("drops unknown ids and keeps catalogue order", () => {
    expect(
      resolveServiceListColumns(["published_at", "not-a-column", "name", "service_id"]),
    ).toEqual(["name", "task_type", "model_name", "tier", "service_id", "published_at", "actions"]);
  });

  it("keeps only the mandatory columns when every optional column is hidden", () => {
    const mandatory = ["name", "task_type", "model_name", "tier", "actions"];
    expect(resolveServiceListColumns(["name", "actions"])).toEqual(mandatory);
    expect(resolveServiceListColumns([])).toEqual(defaults);
    expect(resolveServiceListColumns(null)).toEqual(defaults);
    expect(resolveServiceListColumns(["not-a-column"])).toEqual(defaults);
  });

  it("lets every optional column be hidden and locks the mandatory ones", () => {
    const onlyStatus: ServiceListColumnId[] = [
      "name",
      "task_type",
      "model_name",
      "tier",
      "status",
      "actions",
    ];
    expect(canToggleOffServiceListColumn(onlyStatus, "status")).toBe(true);
    expect(toggleServiceListColumn(onlyStatus, "status")).toEqual(
      onlyStatus.filter((id) => id !== "status"),
    );
    for (const id of ["name", "task_type", "model_name", "tier", "actions"] as const) {
      expect(canToggleOffServiceListColumn(onlyStatus, id)).toBe(false);
      expect(toggleServiceListColumn(onlyStatus, id)).toEqual(onlyStatus);
    }
  });

  it("adds and removes a column immediately, in catalogue order", () => {
    const next = toggleServiceListColumn(defaults, "service_id");
    expect(next).toContain("service_id");
    expect(next.indexOf("created_at")).toBeLessThan(next.indexOf("service_id"));
    expect(next.indexOf("service_id")).toBeLessThan(next.indexOf("actions"));
    expect(toggleServiceListColumn(next, "service_id")).toEqual(defaults);
  });

  it("stores a selection per user and leaves another user's selection alone", () => {
    const store = memoryStore();
    const saved = saveServiceListColumns("user-a", ["name", "service_id", "actions"], store);
    const expected = ["name", "task_type", "model_name", "tier", "service_id", "actions"];
    expect(saved).toEqual(expected);
    expect(loadServiceListColumns("user-a", store)).toEqual(expected);
    expect(loadServiceListColumns("user-b", store)).toEqual(defaults);
    expect(store.data.has("user-b")).toBe(false);
  });

  it("reset writes the default set for that user only", () => {
    const store = memoryStore();
    saveServiceListColumns("user-a", ["service_id"], store);
    const reset = saveServiceListColumns("user-a", defaultServiceListColumnIds(), store);
    expect(reset).toEqual(defaults);
    expect(loadServiceListColumns("user-a", store)).toEqual(defaults);
  });

  it("accepts the columns API ids and drops ones that are not in that catalogue", () => {
    const catalogue: ServiceListColumnDef[] = [
      { id: "name", label: "Name", mandatory: true },
      { id: "task_type", label: "Model Task Type", mandatory: false },
      { id: "actions", label: "Actions", mandatory: true },
    ];
    expect(resolveServiceListColumns(["model_name", "task_type"], catalogue)).toEqual([
      "name",
      "task_type",
      "actions",
    ]);
    expect(defaultServiceListColumnIds(catalogue)).toEqual(["name", "actions"]);
  });

  it("builds filter query params from the catalogue", () => {
    const columns = SERVICE_LIST_COLUMNS;
    expect(
      serviceListFilterParams({
        columns,
        filters: { name: "asr", task_type: "" },
        enabledTaskTypes: "asr,nmt",
      }),
    ).toEqual({ name: "asr", task_types: "asr,nmt" });
    expect(
      serviceListFilterParams({
        columns,
        filters: { name: "", task_type: "llm" },
        enabledTaskTypes: "asr,nmt",
      }),
    ).toEqual({ task_types: "llm" });
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
    expect(loadServiceListColumns("user-a")).toEqual([
      "name",
      "task_type",
      "model_name",
      "tier",
      "actions",
    ]);
    window.localStorage.removeItem(key);
  });

  describe("service-column config", () => {
    // `service-column` config entries, as getServiceColumnConfig returns them.
    const config = [
      { key: "name", label: "Service Name", required: true },
      { key: "modelTaskType", label: "Task Type", required: true },
      { key: "modelName", label: "Model Name", required: true },
      { key: "tier", label: "Tier", required: true },
      // defaultVisible is not used: optional columns always start hidden.
      { key: "status", label: "Status", required: false, defaultVisible: true },
      { key: "created_at", label: "Created At", required: false },
      { key: "serviceId", label: "Service ID", required: false },
      { key: "unknownColumn", label: "Unknown", required: true },
      { key: "actions", label: "Actions", required: true },
    ];

    it("takes the columns, order, labels and mandatory flags from the config", () => {
      const catalogue = serviceListColumnsFromConfig(SERVICE_LIST_COLUMNS, config);
      expect(catalogue.map((column) => column.id)).toEqual([
        "name",
        "task_type",
        "model_name",
        "tier",
        "status",
        "created_at",
        "service_id",
        "actions",
      ]);
      expect(catalogue[0].label).toBe("Service Name");
      expect(defaultServiceListColumnIds(catalogue)).toEqual([
        "name",
        "task_type",
        "model_name",
        "tier",
        "actions",
      ]);
    });

    it("matches camelCase and API-id keys and keeps the catalogue's filters", () => {
      const status = serviceListColumnsFromConfig(SERVICE_LIST_COLUMNS, config).find(
        (column) => column.id === "status",
      );
      const builtIn = SERVICE_LIST_COLUMNS.find((column) => column.id === "status");
      expect(status).toEqual({ ...builtIn, label: "Status", mandatory: false });
    });

    it("appends Actions as mandatory when the config leaves it out", () => {
      const catalogue = serviceListColumnsFromConfig(SERVICE_LIST_COLUMNS, [
        { key: "name", label: "Name", required: true },
        { key: "status", label: "Status", required: false },
      ]);
      expect(catalogue.map((column) => [column.id, column.mandatory])).toEqual([
        ["name", true],
        ["status", false],
        ["actions", true],
      ]);
    });

    it("uses the catalogue as it is without a usable config", () => {
      for (const entries of [undefined, [], [{ key: "unknown", label: "X", required: true }]]) {
        expect(serviceListColumnsFromConfig(SERVICE_LIST_COLUMNS, entries)).toBe(
          SERVICE_LIST_COLUMNS,
        );
      }
    });

    it("lists the mandatory columns in the picker hint", () => {
      expect(mandatoryColumnsHint(serviceListColumnsFromConfig(SERVICE_LIST_COLUMNS, config))).toBe(
        "Service Name, Task Type, Model Name, Tier, and Actions stay visible.",
      );
    });
  });

  describe("columns by role", () => {
    const otherRoleIds = ["name", "task_type", "model_name", "status", "service_id", "actions"];

    it("marks the backend's admin-only columns", () => {
      expect(
        SERVICE_LIST_COLUMNS.filter((column) => column.adminOnly).map((column) => column.id),
      ).toEqual([
        "tier",
        "created_at",
        "input_price",
        "output_price",
        "cached_input_price",
        "published_at",
      ]);
    });

    it("gives Admins and Adopter Admins every column", () => {
      expect(serviceListColumnsForRole(SERVICE_LIST_COLUMNS, true)).toBe(SERVICE_LIST_COLUMNS);
    });

    it("drops the admin-only columns for other roles", () => {
      const catalogue = serviceListColumnsForRole(SERVICE_LIST_COLUMNS, false);
      expect(catalogue.map((column) => column.id)).toEqual(otherRoleIds);
      // Tier is required but admin-only, so other roles have one required column fewer.
      expect(defaultServiceListColumnIds(catalogue)).toEqual([
        "name",
        "task_type",
        "model_name",
        "actions",
      ]);
      expect(mandatoryColumnsHint(catalogue)).toBe(
        "Name, Task Type, Model Name, and Actions stay visible.",
      );
    });

    it("drops admin-only ids from a saved selection", () => {
      const catalogue = serviceListColumnsForRole(SERVICE_LIST_COLUMNS, false);
      expect(resolveServiceListColumns(["tier", "input_price", "status"], catalogue)).toEqual([
        "name",
        "task_type",
        "model_name",
        "status",
        "actions",
      ]);
    });

    it("does not let the config bring admin-only columns back", () => {
      const configured = serviceListColumnsFromConfig(SERVICE_LIST_COLUMNS, [
        { key: "name", label: "Service Name", required: true },
        { key: "tier", label: "Tier", required: true },
        { key: "inputPrice", label: "Input Price", required: false },
        { key: "status", label: "Status", required: false },
      ]);
      expect(serviceListColumnsForRole(configured, false).map((column) => column.id)).toEqual([
        "name",
        "status",
        "actions",
      ]);
      expect(serviceListColumnsForRole(configured, true).map((column) => column.id)).toEqual([
        "name",
        "tier",
        "input_price",
        "status",
        "actions",
      ]);
    });

    it("shows admin-only columns to ADMIN and MODERATOR only", () => {
      expect(seesAdminServiceListColumns(["ADMIN"])).toBe(true);
      expect(seesAdminServiceListColumns(["MODERATOR"])).toBe(true);
      expect(seesAdminServiceListColumns(["moderator"])).toBe(true);
      expect(seesAdminServiceListColumns(["TENANT_ADMIN"])).toBe(false);
      expect(seesAdminServiceListColumns(["USER"])).toBe(false);
      expect(seesAdminServiceListColumns(["USAGE VIEWER"])).toBe(false);
      expect(seesAdminServiceListColumns(undefined)).toBe(false);
    });
  });

  describe("service-column config data", () => {
    // Shape written by the backend migration (b4d6f8a0c2e4), trimmed.
    const stored = [
      {
        columns: [
          {
            id: "name",
            label: "Service Name",
            filter: { type: "text", params: ["name"], options: null },
            sortable: true,
            mandatory: true,
            filterable: true,
            defaultVisible: true,
          },
          {
            id: "actions",
            label: "Actions",
            filter: null,
            sortable: false,
            mandatory: true,
            filterable: false,
            defaultVisible: true,
          },
          {
            id: "task_type",
            label: "Task Type",
            filter: {
              type: "multi_select",
              params: ["task_types"],
              options: [{ label: "asr", value: "asr" }],
            },
            sortable: true,
            mandatory: true,
            filterable: true,
            defaultVisible: true,
          },
          { id: "model_name", label: "Model Name", mandatory: true, sortable: false },
          { id: "tier", label: "Tier", mandatory: true },
          { id: "status", label: "Status", mandatory: false, defaultVisible: true },
          { id: "service_id", label: "Service ID", mandatory: false },
        ],
      },
    ];

    it("reads id, label and mandatory from the columns list", () => {
      expect(parseServiceColumnConfig(stored)).toEqual([
        { key: "name", label: "Service Name", required: true },
        { key: "actions", label: "Actions", required: true },
        { key: "task_type", label: "Task Type", required: true },
        { key: "model_name", label: "Model Name", required: true },
        { key: "tier", label: "Tier", required: true },
        { key: "status", label: "Status", required: false },
        { key: "service_id", label: "Service ID", required: false },
      ]);
    });

    it("builds the Services columns from it, ignoring sortable, filters and defaults", () => {
      const catalogue = serviceListColumnsFromConfig(
        SERVICE_LIST_COLUMNS,
        parseServiceColumnConfig(stored),
      );
      expect(catalogue.map((column) => column.id)).toEqual([
        "name",
        "actions",
        "task_type",
        "model_name",
        "tier",
        "status",
        "service_id",
      ]);
      expect(defaultServiceListColumnIds(catalogue)).toEqual([
        "name",
        "actions",
        "task_type",
        "model_name",
        "tier",
      ]);
      // Filters stay with the built-in columns (no config options).
      const taskType = catalogue.find((column) => column.id === "task_type");
      expect(taskType?.filter?.options).toBeNull();
      // sortable: false in the config does not change the fixed sortable list.
      expect(SERVICE_SORTABLE_COLUMN_IDS.has("model_name")).toBe(true);
    });

    it("rejects other shapes so the built-in columns are used", () => {
      expect(() =>
        parseServiceColumnConfig([{ key: "name", label: "Name", required: true }]),
      ).toThrow();
      expect(() => parseServiceColumnConfig([{ id: "name", mandatory: true }])).toThrow();
      expect(parseServiceColumnConfig([])).toEqual([]);
    });
  });
});
