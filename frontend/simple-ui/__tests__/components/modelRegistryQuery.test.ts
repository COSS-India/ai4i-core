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
      versionStatus: undefined,
      taskTypes: "nmt,llm",
      sortBy: undefined,
      sortOrder: undefined,
    });
  });

  it("maps the name search and the Status / Task Type filters to query params", () => {
    const params = buildModelListParams({
      ...base,
      filters: { name: " gemma ", status: "deprecated", taskType: "llm" },
    });
    expect(params).toMatchObject({
      name: "gemma",
      versionStatus: "deprecated",
      taskTypes: "llm",
    });
  });

  it("drops filters the page does not send to the API", () => {
    expect(
      modelServerFilters({ noOfServices: "2", name: "", version: "v1", status: "active" }),
    ).toEqual({ status: "active" });
  });

  it("sorts by the page's sortable columns, but not by others", () => {
    expect(
      buildModelListParams({ ...base, sort: { key: "createdAt", direction: "desc" } }),
    ).toMatchObject({ sortBy: "createdAt", sortOrder: "desc" });
    expect(
      buildModelListParams({ ...base, sort: { key: "noOfServices", direction: "asc" } }).sortBy,
    ).toBeUndefined();
    expect(
      buildModelListParams({ ...base, sort: { key: "actions", direction: "asc" } }).sortBy,
    ).toBeUndefined();
  });

  it("omits task_types when no task types are enabled", () => {
    expect(buildModelListParams({ ...base, enabledTaskTypes: [] }).taskTypes).toBeUndefined();
  });
});
