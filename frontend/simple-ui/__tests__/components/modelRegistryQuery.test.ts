import {
  buildModelListParams,
  modelServerFilters,
} from "../../src/components/model-management/modelRegistryQuery";

const base = {
  filters: {},
  enabledTaskTypes: ["nmt", "llm"],
  sort: { key: "", direction: "asc" as const },
  page: 1,
  pageSize: 25,
  columns: "name,version,taskType,actions",
};

describe("model registry query (GET /models/list)", () => {
  it("pages with offset/limit and keeps the API default order when no column is sorted", () => {
    expect(buildModelListParams({ ...base, page: 3 })).toEqual({
      offset: 50,
      limit: 25,
      columns: "name,version,taskType,actions",
      name: undefined,
      version: undefined,
      providerName: undefined,
      versionStatus: undefined,
      taskTypes: "nmt,llm",
      createdFrom: undefined,
      createdTo: undefined,
      sortBy: undefined,
      sortOrder: undefined,
    });
  });

  it("maps every server-backed column search to its query param", () => {
    const params = buildModelListParams({
      ...base,
      filters: {
        name: " gemma ",
        version: "v2",
        providerName: "Example",
        status: "deprecated",
        taskType: "llm",
        createdAt: "2026-09-01~2026-09-30",
      },
    });
    expect(params).toMatchObject({
      name: "gemma",
      version: "v2",
      providerName: "Example",
      versionStatus: "deprecated",
      taskTypes: "llm",
      createdFrom: "2026-09-01",
      createdTo: "2026-09-30",
    });
  });

  it("sends an open-ended date range", () => {
    const params = buildModelListParams({
      ...base,
      filters: { createdAt: "2026-09-01~" },
    });
    expect(params.createdFrom).toBe("2026-09-01");
    expect(params.createdTo).toBeUndefined();
  });

  it("drops filters the API cannot use", () => {
    expect(modelServerFilters({ noOfServices: "2", name: "", version: "v1" })).toEqual({
      version: "v1",
    });
  });

  it("sorts by any data column, but not by Actions", () => {
    expect(
      buildModelListParams({ ...base, sort: { key: "noOfServices", direction: "desc" } }),
    ).toMatchObject({ sortBy: "noOfServices", sortOrder: "desc" });
    expect(
      buildModelListParams({ ...base, sort: { key: "actions", direction: "asc" } }).sortBy,
    ).toBeUndefined();
  });

  it("omits task_types when no task types are enabled", () => {
    expect(buildModelListParams({ ...base, enabledTaskTypes: [] }).taskTypes).toBeUndefined();
  });
});
