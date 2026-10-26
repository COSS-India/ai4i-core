import { formatModelTaskTypeLabel, SERVICE_TIER } from "../../config/constants";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type {
  DataTableFilterDef,
  DataTableSearchConfig,
} from "../common/dataTableTypes";
import {
  serviceListCellKey,
  serviceListRangeFilterKeys,
  type ServiceListColumnDef,
} from "./serviceListColumns";

type SelectOption = { label: string; value: string };

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
  };
}

function buildDateRangeFilterDefs(
  column: ServiceListColumnDef,
  serverFilterValues: Record<string, string> | undefined,
  onChange: (columnId: string, value: string) => void,
): DataTableFilterDef[] {
  const params = column.filter?.params ?? [];
  if (params.length < 2) return [];
  const keys = serviceListRangeFilterKeys(column.id);
  return [
    {
      id: keys.from,
      label: `${column.label} from`,
      type: "date",
      param: params[0],
      inputType: "date",
      value: serverFilterValues?.[keys.from] ?? "",
      onChange: (next) => onChange(keys.from, next),
    },
    {
      id: keys.to,
      label: `${column.label} to`,
      type: "date",
      param: params[1],
      inputType: "date",
      value: serverFilterValues?.[keys.to] ?? "",
      onChange: (next) => onChange(keys.to, next),
    },
  ];
}

function buildTextFilterDef(
  column: ServiceListColumnDef,
  value: string,
  onChange: (columnId: string, value: string) => void,
): DataTableFilterDef {
  return {
    id: column.id,
    label: column.label,
    type: "text",
    param: column.filter?.params[0],
    value,
    onChange: (next) => onChange(column.id, next),
  };
}

export function buildServerServiceFilterDefs(options: {
  columns: readonly ServiceListColumnDef[];
  nameColumnId?: string;
  serverFilterValues?: Record<string, string>;
  taskTypeNames: string[];
  tierFilterOptions: ServiceTierFilterOption[];
  onChange: (columnId: string, value: string) => void;
}): DataTableFilterDef[] {
  const defs: DataTableFilterDef[] = [];
  for (const column of options.columns) {
    if (!column.filterable || !column.filter) continue;
    if (column.id === options.nameColumnId) continue;

    const value = options.serverFilterValues?.[column.id] ?? "";
    const kind = column.filter.type;

    if (kind === "single_select" || kind === "multi_select") {
      defs.push(
        buildSelectFilterDef(
          column,
          value,
          options.taskTypeNames,
          options.tierFilterOptions,
          options.onChange,
        ),
      );
      continue;
    }

    if (kind === "date_range") {
      defs.push(
        ...buildDateRangeFilterDefs(
          column,
          options.serverFilterValues,
          options.onChange,
        ),
      );
      continue;
    }

    if (kind === "text") {
      defs.push(buildTextFilterDef(column, value, options.onChange));
    }
  }
  return defs;
}

export function buildClientServiceFilterDefs(options: {
  filterStatus: string;
  onFilterStatusChange: (value: string) => void;
  filterTaskType: string;
  onFilterTaskTypeChange: (value: string) => void;
  taskTypeNames: string[];
  filterTier: string;
  onFilterTierChange: (value: string) => void;
  tierFilterOptions: ServiceTierFilterOption[];
}): DataTableFilterDef[] {
  const taskOptions: SelectOption[] = options.taskTypeNames.map((taskType) => ({
    label: formatModelTaskTypeLabel(taskType),
    value: taskType,
  }));
  if (options.taskTypeNames.length > 1) {
    taskOptions.unshift({ label: "All", value: "" });
  }
  const tierOptions: SelectOption[] = [
    { label: "All", value: SERVICE_TIER.FILTER.ALL },
    ...options.tierFilterOptions.map((tier) => ({
      label: tier.name,
      value: tier.id,
    })),
    { label: "No tier", value: SERVICE_TIER.FILTER.NONE },
  ];
  return [
    {
      id: "status",
      label: "Status",
      type: "select",
      param: "status",
      value: options.filterStatus,
      onChange: options.onFilterStatusChange,
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
      options: taskOptions,
    },
    {
      id: "tier",
      label: "Tier",
      type: "select",
      value: options.filterTier,
      onChange: options.onFilterTierChange,
      options: tierOptions,
    },
  ];
}

export function buildServiceRegistrySearch(options: {
  serverMode: boolean;
  nameColumn?: ServiceListColumnDef;
  serverFilterValues?: Record<string, string>;
  onServerFilterChange?: (columnId: string, value: string) => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
}): DataTableSearchConfig | undefined {
  if (!options.serverMode) {
    return {
      label: "Search",
      value: options.searchQuery,
      onChange: options.onSearchQueryChange,
      placeholder: "Search by service name...",
      fields: ["service_name", "name"],
    };
  }

  const nameColumn = options.nameColumn;
  if (!nameColumn || !options.onServerFilterChange) return undefined;

  return {
    label: nameColumn.label,
    value: options.serverFilterValues?.[nameColumn.id] ?? "",
    onChange: (value) => options.onServerFilterChange?.(nameColumn.id, value),
    placeholder: "Search by service name...",
    debounceMs: 400,
    fields: ["name"],
  };
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
