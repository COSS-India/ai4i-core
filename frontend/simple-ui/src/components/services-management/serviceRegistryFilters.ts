import { formatModelTaskTypeLabel } from "../../config/constants";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { Service } from "../../types/platform";
import type { DataTableFilterDef } from "../common/dataTableTypes";
import {
  serviceListCellKey,
  serviceListServiceId,
  serviceModelName,
  type ServiceListColumnDef,
} from "./serviceListColumns";

type SelectOption = { label: string; value: string };

/** Toolbar keeps only Status and Task Type — everything else is column search. */
const TOOLBAR_FILTER_ORDER = ["status", "task"] as const;

/**
 * Column search that maps to server filter params.
 * Status and task type stay on the toolbar selects only.
 */
export const SERVICE_COLUMN_SEARCH_KEYS = new Set([
  "name",
  "tier",
  "modelName",
  "serviceId",
]);

function selectOptionsForColumn(
  column: ServiceListColumnDef,
  taskTypeNames: string[],
  tierFilterOptions: ServiceTierFilterOption[],
): SelectOption[] {
  const apiOptions = column.filter?.options ?? [];
  const cellKey = serviceListCellKey(column.id);

  if (cellKey === "task") {
    return taskTypeNames
      .filter(
        (name) =>
          apiOptions.length === 0 ||
          apiOptions.some(
            (option) => option.value.toLowerCase() === name.toLowerCase(),
          ),
      )
      .map((name) => ({
        label: formatModelTaskTypeLabel(name),
        value: name,
      }));
  }

  if (cellKey === "tier" && apiOptions.length === 0) {
    return tierFilterOptions.map((tier) => ({
      label: tier.name,
      value: tier.id,
    }));
  }

  return apiOptions;
}

function buildSelectFilterDef(
  column: ServiceListColumnDef,
  value: string,
  taskTypeNames: string[],
  tierFilterOptions: ServiceTierFilterOption[],
  onChange: (columnId: string, value: string) => void,
): DataTableFilterDef {
  const cellKey = serviceListCellKey(column.id);
  const showAll = cellKey !== "task" || taskTypeNames.length > 1;
  let selectedValue = value;
  if (cellKey === "task" && taskTypeNames.length === 1) {
    selectedValue = taskTypeNames[0];
  }
  const options: SelectOption[] = [
    ...selectOptionsForColumn(column, taskTypeNames, tierFilterOptions),
  ];
  if (showAll) {
    options.unshift({ label: "All", value: "" });
  }

  return {
    id: column.id,
    label: column.label,
    type: "select",
    param: column.filter?.params[0],
    value: selectedValue,
    onChange: (next) => onChange(column.id, next),
    options,
    width: { base: "full", sm: selectFilterWidth(cellKey) },
  };
}

function selectFilterWidth(cellKey: string): string {
  if (cellKey === "task") return "168px";
  if (cellKey === "status") return "132px";
  return "160px";
}

/** Name search only. Model name and service id are their own filters. */
export function serviceMatchesSearch(service: Service, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (service.name ?? "").toLowerCase().includes(q);
}

export function serviceMatchesRegistryFilters(
  service: Service,
  filters: { query: string; modelName: string; serviceId: string },
): boolean {
  if (!serviceMatchesSearch(service, filters.query)) return false;
  if (filters.modelName && serviceModelName(service) !== filters.modelName) return false;
  if (filters.serviceId && serviceListServiceId(service) !== filters.serviceId) return false;
  return true;
}

export function serviceSelectOptions(values: readonly string[]): SelectOption[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)))
    .sort((left, right) => left.localeCompare(right))
    .map((value) => ({ label: value, value }));
}

export function buildServerServiceFilterDefs(options: {
  columns: readonly ServiceListColumnDef[];
  serverFilterValues?: Record<string, string>;
  taskTypeNames: string[];
  tierFilterOptions: ServiceTierFilterOption[];
  onChange: (columnId: string, value: string) => void;
}): DataTableFilterDef[] {
  const defs: DataTableFilterDef[] = [];
  for (const column of options.columns) {
    if (!column.filterable || !column.filter) continue;
    const cellKey = serviceListCellKey(column.id);
    if (
      !TOOLBAR_FILTER_ORDER.includes(
        cellKey as (typeof TOOLBAR_FILTER_ORDER)[number],
      )
    ) {
      continue;
    }
    if (
      column.filter.type !== "single_select" &&
      column.filter.type !== "multi_select"
    ) {
      continue;
    }

    const def = buildSelectFilterDef(
      column,
      options.serverFilterValues?.[column.id] ?? "",
      options.taskTypeNames,
      options.tierFilterOptions,
      options.onChange,
    );
    if (cellKey === "task") def.label = "Task Type";
    defs.push(def);
  }
  defs.sort(
    (left, right) =>
      TOOLBAR_FILTER_ORDER.indexOf(
        serviceListCellKey(left.id) as (typeof TOOLBAR_FILTER_ORDER)[number],
      ) -
      TOOLBAR_FILTER_ORDER.indexOf(
        serviceListCellKey(right.id) as (typeof TOOLBAR_FILTER_ORDER)[number],
      ),
  );
  return defs;
}

export function buildClientServiceFilterDefs(options: {
  filterStatus: string;
  onFilterStatusChange: (value: string) => void;
  filterTaskType: string;
  onFilterTaskTypeChange: (value: string) => void;
  taskTypeNames: string[];
}): DataTableFilterDef[] {
  const taskOptions: SelectOption[] = options.taskTypeNames.map((taskType) => ({
    label: formatModelTaskTypeLabel(taskType),
    value: taskType,
  }));
  if (options.taskTypeNames.length > 1) {
    taskOptions.unshift({ label: "All", value: "" });
  }
  return [
    {
      id: "status",
      label: "Status",
      type: "select",
      param: "status",
      value: options.filterStatus,
      onChange: options.onFilterStatusChange,
      width: { base: "full", sm: "132px" },
      options: [
        { label: "All", value: "" },
        { label: "Published", value: "published" },
        { label: "Unpublished", value: "unpublished" },
      ],
    },
    {
      id: "taskType",
      label: "Task Type",
      type: "select",
      param: "model_task_type",
      value: options.filterTaskType,
      onChange: options.onFilterTaskTypeChange,
      width: { base: "full", sm: "168px" },
      options: taskOptions,
    },
  ];
}

export function statusFilterToPublished(status: string): boolean | undefined {
  if (status === "published") return true;
  if (status === "unpublished") return false;
  return undefined;
}

export function statusFilterToApiValue(status: string): string {
  if (status === "published") return "true";
  if (status === "unpublished") return "false";
  return "";
}
