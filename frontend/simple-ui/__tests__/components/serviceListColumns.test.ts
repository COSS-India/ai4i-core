import {
  browserServiceListColumnStore,
  canToggleOffServiceListColumn,
  defaultServiceListColumnIds,
  loadServiceListColumns,
  resolveServiceListColumns,
  saveServiceListColumns,
  serviceListColumnStorageKey,
  toggleServiceListColumn,
  type ServiceListColumnId,
  type ServiceListColumnPreferenceStore,
} from "../../src/components/services-management/serviceListColumns";

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
