import React from "react";
import {
  activeColumnFilterCount,
  applyColumnFilters,
  setColumnFilterValue,
  withAutoColumnFilters,
  withAutoColumnSort,
  type FilterableColumn,
} from "../../src/components/common/DataTableColumnFilter";
import {
  columnFiltersToTraceParams,
  logsColumnFilterConfig,
  validateStatusCodes,
} from "../../src/utils/logsDashboard";

type Row = { id: string; name: string; status: string; tags?: string[] };

const rows: Row[] = [
  { id: "1", name: "Alpha Service", status: "active", tags: ["asr"] },
  { id: "2", name: "beta", status: "inactive", tags: ["nmt", "tts"] },
  { id: "3", name: "Gamma alpha", status: "active" },
];

const columns: FilterableColumn<Row>[] = [
  { id: "name", header: "Name", filter: { type: "text" } },
  {
    id: "status",
    header: "Status",
    filter: { type: "select", options: [{ label: "Active", value: "active" }] },
  },
  { id: "tags", header: "Tags", filter: { type: "text" } },
  { id: "id", header: "ID" },
];

describe("withAutoColumnSort", () => {
  it("makes every data column sortable except Actions", () => {
    const result = withAutoColumnSort<Row, FilterableColumn<Row> & { sortable?: boolean }>([
      { id: "name", header: "Name" },
      { id: "status", header: "Status", sortable: false },
      { id: "actions", header: "Actions" },
      { id: "row-actions", header: "Actions" },
    ]);
    expect(result.map((c) => c.sortable)).toEqual([true, true, false, false]);
  });

  it("disables sort for columns owned by toolbar select filters", () => {
    const result = withAutoColumnSort<Row, FilterableColumn<Row> & { sortable?: boolean }>(
      [
        { id: "latency", header: "Latency" },
        { id: "status", header: "Status" },
        { id: "task_type", header: "Task Type" },
        { id: "institution", header: "Institution" },
        { id: "method", header: "Method" },
        { id: "timestamp", header: "Timestamp" },
        { id: "actions", header: "Actions" },
      ],
      [
        { id: "status", type: "select" },
        { id: "taskType", type: "select" },
        { id: "tenant", type: "select" },
        { id: "method", type: "select" },
        { id: "q", type: "text" },
      ],
    );
    expect(result.find((c) => c.id === "latency")?.sortable).toBe(true);
    expect(result.find((c) => c.id === "timestamp")?.sortable).toBe(true);
    expect(result.find((c) => c.id === "status")?.sortable).toBe(false);
    expect(result.find((c) => c.id === "task_type")?.sortable).toBe(false);
    expect(result.find((c) => c.id === "institution")?.sortable).toBe(false);
    expect(result.find((c) => c.id === "method")?.sortable).toBe(false);
    expect(result.find((c) => c.id === "actions")?.sortable).toBe(false);
  });
});

describe("withAutoColumnFilters", () => {
  it("adds text search to every column, keeping explicit configs and opt-outs", () => {
    const result = withAutoColumnFilters<Row, FilterableColumn<Row>>(
      [
        { id: "name", header: "Name" },
        { id: "status", header: "Status", filter: { type: "select", options: [] } },
        { id: "id", header: "ID", filter: false },
        { id: "actions", header: "" },
        { id: "row-actions", header: "Actions" },
      ],
      "page only",
    );
    expect(result.map((c) => c.filter)).toEqual([
      { type: "text", helper: "page only" },
      { type: "select", options: [] },
      false,
      undefined,
      undefined,
    ]);
  });

  it("searches the rendered cell text as well as the raw value", () => {
    const cols = withAutoColumnFilters<Row, FilterableColumn<Row>>([
      {
        id: "status",
        header: "Status",
        cell: (row) => React.createElement("span", null, row.status === "active" ? "Live" : "Off"),
      },
    ]);
    expect(applyColumnFilters(rows, cols, { status: "live" }).map((r) => r.id)).toEqual(["1", "3"]);
    expect(applyColumnFilters(rows, cols, { status: "inact" }).map((r) => r.id)).toEqual(["2"]);
  });
});

describe("applyColumnFilters", () => {
  it("matches text columns case-insensitively by substring", () => {
    expect(applyColumnFilters(rows, columns, { name: "ALPHA" }).map((r) => r.id)).toEqual([
      "1",
      "3",
    ]);
  });

  it("matches select columns exactly and combines columns with AND", () => {
    const result = applyColumnFilters(rows, columns, { status: "active", name: "gamma" });
    expect(result.map((r) => r.id)).toEqual(["3"]);
  });

  it("searches array values and ignores columns without a filter config", () => {
    expect(applyColumnFilters(rows, columns, { tags: "tts" }).map((r) => r.id)).toEqual(["2"]);
    expect(applyColumnFilters(rows, columns, { id: "2" })).toHaveLength(3);
  });
});

describe("setColumnFilterValue", () => {
  it("trims values and drops empty ones", () => {
    const next = setColumnFilterValue({ name: "x" }, "status", "  active ");
    expect(next).toEqual({ name: "x", status: "active" });
    expect(setColumnFilterValue(next, "name", "  ")).toEqual({ status: "active" });
    expect(activeColumnFilterCount({ a: "1", b: "" })).toBe(1);
  });
});

describe("logs column filters", () => {
  const def = (key: string, filterable: boolean) => ({
    key,
    label: key,
    default: false,
    filterable,
    sortable: false,
    keyword_searchable: true,
  });

  it("leaves toolbar selects without a column box and searches latency", () => {
    expect(logsColumnFilterConfig(def("status", true))).toBe(false);
    expect(logsColumnFilterConfig(def("method", true))).toBe(false);
    expect(logsColumnFilterConfig(def("task_type", true))).toBe(false);
    expect(logsColumnFilterConfig(def("institution", true))).toBe(false);
    expect(logsColumnFilterConfig(def("timestamp", true))).toBe(false);
    expect(logsColumnFilterConfig(def("latency", true))).toMatchObject({
      type: "text",
    });
    expect(logsColumnFilterConfig(def("end_user", true))).toBeDefined();
  });

  it("maps column searches to traces/search params", () => {
    expect(
      columnFiltersToTraceParams({
        end_user: "u-1",
        service: "svc",
        status_code: "500, 503",
        metadata: "env = prod",
        url: "/v1/asr",
      }),
    ).toMatchObject({
      user: "u-1",
      serviceId: "svc",
      statusCode: "500,503",
      metadataKey: "env",
      metadataValue: "prod",
      url: "/v1/asr",
    });
  });

  it("validates status codes", () => {
    expect(validateStatusCodes("500,503")).toBeUndefined();
    expect(validateStatusCodes("50")).toBeDefined();
    expect(validateStatusCodes("700")).toBeDefined();
  });
});
