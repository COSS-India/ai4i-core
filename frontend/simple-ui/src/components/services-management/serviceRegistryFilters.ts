import { formatModelTaskTypeLabel, SERVICE_TIER } from "../../config/constants";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type {
  DataTableFilterDef,
  DataTableSearchConfig,
} from "../common/dataTableTypes";
import {
  serviceListCellKey,
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
    width: { base: "full", sm: selectFilterWidth(cellKey) },
  };
}

function selectFilterWidth(cellKey: string): string {
  if (cellKey === "task") return "168px";
  if (cellKey === "status") return "132px";
  if (cellKey === "tier") return "140px";
  return "160px";
}

const TOOLBAR_FILTER_ORDER = ["status", "task", "tier"] as const;

export function buildServerServiceFilterDefs(options: {
  columns: readonly ServiceListColumnDef[];
  serverFilterValues?: Record<string, string>;
  taskTypeNames: string[];
  tierFilterOptions: ServiceTierFilterOption[];
  onChange: (columnId: string, value: string) => void;
}): DataTableFilterDef[] {
  const byKey = new Map<string, DataTableFilterDef>();
  for (const column of options.columns) {
    if (!column.filterable || !column.filter) continue;
    const kind = column.filter.type;
    if (kind !== "single_select" && kind !== "multi_select") continue;
    const cellKey = serviceListCellKey(column.id);
    if (!TOOLBAR_FILTER_ORDER.includes(cellKey as (typeof TOOLBAR_FILTER_ORDER)[number])) continue;
    byKey.set(
      cellKey,
      buildSelectFilterDef(
        column,
        options.serverFilterValues?.[column.id] ?? "",
        options.taskTypeNames,
        options.tierFilterOptions,
        options.onChange,
      ),
    );
  }
  return TOOLBAR_FILTER_ORDER.flatMap((key) => {
    const def = byKey.get(key);
    return def ? [def] : [];
  });
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
    {
      id: "tier",
      label: "Tier",
      type: "select",
      value: options.filterTier,
      onChange: options.onFilterTierChange,
      width: { base: "full", sm: "140px" },
      options: tierOptions,
    },
  ];
}

export function buildServiceRegistrySearch(options: {
  serverMode: boolean;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
}): DataTableSearchConfig {
  return {
    label: "Search",
    value: options.searchQuery,
    onChange: options.onSearchQueryChange,
    placeholder: "Search by service name...",
    width: { base: "full", sm: "240px" },
    debounceMs: options.serverMode ? 400 : undefined,
    fields: ["name", "model_name", "service_id"],
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
