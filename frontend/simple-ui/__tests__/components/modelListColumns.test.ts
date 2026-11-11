import {
  browserModelListColumnStore,
  canToggleOffModelListColumn,
  MODEL_LIST_COLUMNS,
  defaultModelListColumnIds,
  loadModelListColumns,
  modelListColumnsFromConfig,
  modelListColumnsParam,
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

  it("starts with Name, Version, Task Type, Provider Name and Actions", () => {
    expect(defaults).toEqual(["name", "version", "taskType", "providerName", "actions"]);
  });

  it("drops unknown ids and keeps catalogue order", () => {
    expect(
      resolveModelListColumns(["noOfServices", "not-a-column", "name", "status"]),
    ).toEqual(["name", "status", "noOfServices", "actions"]);
  });

  it("keeps a mandatory-only selection and restores defaults only when nothing usable is stored", () => {
    const mandatoryOnly = ["name", "actions"];
    expect(resolveModelListColumns(mandatoryOnly)).toEqual(mandatoryOnly);
    expect(resolveModelListColumns(["not-a-column"])).toEqual(defaults);
    expect(resolveModelListColumns([])).toEqual(defaults);
    expect(resolveModelListColumns(null)).toEqual(defaults);
  });

  it("locks only Name and Actions in the built-in catalogue", () => {
    expect(
      MODEL_LIST_COLUMNS.filter((column) => column.mandatory).map((column) => column.id),
    ).toEqual(["name", "actions"]);
  });

  it("locks only mandatory columns, so the last optional column can be hidden", () => {
    const onlyStatus: ModelListColumnId[] = ["name", "status", "actions"];
    expect(canToggleOffModelListColumn(onlyStatus, "status")).toBe(true);
    expect(toggleModelListColumn(onlyStatus, "status")).toEqual(["name", "actions"]);
    expect(canToggleOffModelListColumn(onlyStatus, "version")).toBe(true);
    expect(canToggleOffModelListColumn(onlyStatus, "name")).toBe(false);
    expect(toggleModelListColumn(onlyStatus, "name")).toEqual(onlyStatus);
  });

  it("can turn every optional column off and back on by hand", () => {
    const optional = ["version", "taskType", "providerName", "status", "createdAt", "noOfServices"];
    const all = MODEL_LIST_COLUMNS.map((column) => column.id);
    let visible = resolveModelListColumns(all);
    for (const id of optional) {
      visible = toggleModelListColumn(visible, id);
    }
    expect(visible).toEqual(["name", "actions"]);
    for (const id of optional) {
      visible = toggleModelListColumn(visible, id);
    }
    expect(visible).toEqual(all);
  });

  it("adds and removes a column immediately, in catalogue order", () => {
    const withoutServices = resolveModelListColumns([
      "name",
      "version",
      "taskType",
      "providerName",
      "status",
      "createdAt",
      "actions",
    ]);
    const next = toggleModelListColumn(withoutServices, "noOfServices");
    expect(next).toContain("noOfServices");
    expect(next.indexOf("createdAt")).toBeLessThan(next.indexOf("noOfServices"));
    expect(next.indexOf("noOfServices")).toBeLessThan(next.indexOf("actions"));
    expect(toggleModelListColumn(next, "noOfServices")).toEqual(withoutServices);
  });

  it("stores a selection per user and leaves another user's selection alone", () => {
    const store = memoryStore();
    const saved = saveModelListColumns(
      "user-a",
      ["name", "version", "taskType", "providerName", "status", "actions"],
      store,
    );
    expect(saved).toEqual([
      "name",
      "version",
      "taskType",
      "providerName",
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

  it("builds the catalogue from the model-column config", () => {
    const catalogue = modelListColumnsFromConfig([
      { key: "name", label: "Model", required: true },
      { key: "status", label: "State", required: false },
      { key: "unknownColumn", label: "Unknown", required: false },
      { key: "name", label: "Duplicate", required: false },
      { key: "actions", label: "Actions", required: true },
    ]);
    expect(catalogue).toEqual([
      { id: "name", label: "Model", mandatory: true, defaultVisible: true },
      { id: "status", label: "State", mandatory: false, defaultVisible: false },
      { id: "actions", label: "Actions", mandatory: true, defaultVisible: true },
    ]);
    expect(defaultModelListColumnIds(catalogue)).toEqual(["name", "actions"]);
  });

  it("takes mandatory columns from the config's required flag and the built-in default set", () => {
    const catalogue = modelListColumnsFromConfig([
      { key: "name", label: "Name", required: true },
      { key: "version", label: "Version", required: false },
      { key: "taskType", label: "Task Type", required: false },
      { key: "providerName", label: "Provider Name", required: false },
      { key: "status", label: "Status", required: false },
      { key: "actions", label: "Actions", required: true },
    ]);
    expect(
      catalogue.filter((column) => column.mandatory).map((column) => column.id),
    ).toEqual(["name", "actions"]);
    const reset = defaultModelListColumnIds(catalogue);
    expect(reset).toEqual(["name", "version", "taskType", "providerName", "actions"]);
    expect(canToggleOffModelListColumn(reset, "version", catalogue)).toBe(true);
  });

  it("lets the config's defaultVisible override the built-in default", () => {
    const catalogue = modelListColumnsFromConfig([
      { key: "name", label: "Name", required: true },
      { key: "version", label: "Version", required: false, defaultVisible: false },
      { key: "status", label: "Status", required: false, defaultVisible: true },
      { key: "actions", label: "Actions", required: true },
    ]);
    expect(defaultModelListColumnIds(catalogue)).toEqual(["name", "status", "actions"]);
  });

  it("appends Actions when the config leaves it out", () => {
    const catalogue = modelListColumnsFromConfig([
      { key: "name", label: "Name", required: true },
      { key: "status", label: "Status", required: false },
    ]);
    expect(catalogue.map((column) => column.id)).toEqual(["name", "status", "actions"]);
    expect(catalogue.at(-1)).toMatchObject({ id: "actions", mandatory: true });
  });

  it("falls back to the built-in catalogue when the config is empty or unknown", () => {
    expect(modelListColumnsFromConfig(undefined)).toBe(MODEL_LIST_COLUMNS);
    expect(modelListColumnsFromConfig([])).toBe(MODEL_LIST_COLUMNS);
    expect(
      modelListColumnsFromConfig([{ key: "nope", label: "Nope", required: true }]),
    ).toBe(MODEL_LIST_COLUMNS);
  });

  it("requests the visible columns plus the ones the actions need", () => {
    expect(modelListColumnsParam(["name", "status", "noOfServices"])).toBe(
      "name,status,noOfServices,version,actions",
    );
    expect(modelListColumnsParam(defaults)).toBe(defaults.join(","));
  });

  it("builds a per-user storage key", () => {
    expect(modelListColumnStorageKey("u1")).toBe("model-list-columns:u1");
    expect(browserModelListColumnStore.read("")).toBeNull();
  });
});
