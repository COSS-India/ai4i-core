import {
  browserModelListColumnStore,
  canToggleOffModelListColumn,
  defaultModelListColumnIds,
  loadModelListColumns,
  modelListColumnStorageKey,
  resolveModelListColumns,
  saveModelListColumns,
  toggleModelListColumn,
  type ModelListColumnDef,
  type ModelListColumnId,
  type ModelListColumnPreferenceStore,
} from "../../src/components/model-management/modelListColumns";

const memoryStore = (): ModelListColumnPreferenceStore & {
  data: Map<string, string[]>;
} => {
  const data = new Map<string, string[]>();
  return {
    data,
    read: (userId) => data.get(userId) ?? null,
    write: (userId, columnIds) => {
      data.set(userId, [...columnIds]);
    },
  };
};

describe("model list columns (AI4IDS-3351)", () => {
  const defaults = defaultModelListColumnIds();

  it("starts with the default set, including mandatory columns", () => {
    expect(defaults).toEqual([
      "name",
      "version",
      "task",
      "provider",
      "status",
      "created",
      "serviceCount",
      "actions",
    ]);
  });

  it("drops unknown ids and keeps catalogue order", () => {
    expect(
      resolveModelListColumns(["serviceCount", "not-a-column", "name", "status"]),
    ).toEqual(["name", "version", "task", "provider", "status", "serviceCount", "actions"]);
  });

  it("restores defaults when only mandatory columns are stored", () => {
    expect(
      resolveModelListColumns(["name", "version", "task", "provider", "actions"]),
    ).toEqual(defaults);
    expect(resolveModelListColumns([])).toEqual(defaults);
    expect(resolveModelListColumns(null)).toEqual(defaults);
  });

  it("refuses to hide the last flexible column", () => {
    const onlyStatus: ModelListColumnId[] = [
      "name",
      "version",
      "task",
      "provider",
      "status",
      "actions",
    ];
    expect(canToggleOffModelListColumn(onlyStatus, "status")).toBe(false);
    expect(toggleModelListColumn(onlyStatus, "status")).toEqual(onlyStatus);
    expect(canToggleOffModelListColumn(onlyStatus, "name")).toBe(false);
  });

  it("adds and removes a column immediately, in catalogue order", () => {
    const withoutServices = resolveModelListColumns([
      "name",
      "version",
      "task",
      "provider",
      "status",
      "created",
      "actions",
    ]);
    const next = toggleModelListColumn(withoutServices, "serviceCount");
    expect(next).toContain("serviceCount");
    expect(next.indexOf("created")).toBeLessThan(next.indexOf("serviceCount"));
    expect(next.indexOf("serviceCount")).toBeLessThan(next.indexOf("actions"));
    expect(toggleModelListColumn(next, "serviceCount")).toEqual(withoutServices);
  });

  it("stores a selection per user and leaves another user's selection alone", () => {
    const store = memoryStore();
    const saved = saveModelListColumns(
      "user-a",
      ["name", "version", "task", "provider", "status", "actions"],
      store,
    );
    expect(saved).toEqual([
      "name",
      "version",
      "task",
      "provider",
      "status",
      "actions",
    ]);
    expect(loadModelListColumns("user-a", store)).toEqual(saved);
    expect(loadModelListColumns("user-b", store)).toEqual(defaults);
    expect(store.data.has("user-b")).toBe(false);
  });

  it("reset writes the default set for that user only", () => {
    const store = memoryStore();
    saveModelListColumns("user-a", ["status"], store);
    const reset = saveModelListColumns("user-a", defaultModelListColumnIds(), store);
    expect(reset).toEqual(defaults);
    expect(loadModelListColumns("user-a", store)).toEqual(defaults);
  });

  it("accepts a custom catalogue from the API shape", () => {
    const catalogue: ModelListColumnDef[] = [
      { id: "name", label: "Name", mandatory: true, defaultVisible: true },
      { id: "task_type", label: "Task Type", mandatory: true, defaultVisible: true },
      { id: "status", label: "Status", mandatory: false, defaultVisible: true },
      { id: "actions", label: "Actions", mandatory: true, defaultVisible: true },
    ];
    expect(resolveModelListColumns(["status", "task_type"], catalogue)).toEqual([
      "name",
      "task_type",
      "status",
      "actions",
    ]);
  });

  it("builds a per-user storage key", () => {
    expect(modelListColumnStorageKey("u1")).toBe("model-list-columns:u1");
    expect(browserModelListColumnStore.read("")).toBeNull();
  });
});
