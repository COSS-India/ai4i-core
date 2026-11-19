import { formatModelTaskTypeLabel } from "../../config/constants";
import type { ServiceTierFilterOption } from "../../hooks/useServicesManagement";
import type { DataTableFilterDef } from "../common/dataTableTypes";
import {
  serviceListCellKey,
  type ServiceListColumnDef,
} from "./serviceListColumns";

type SelectOption = { label: string; value: string };

/** Toolbar select filters: Status and Task Type (name has its own search box). */
const TOOLBAR_FILTER_ORDER = ["status", "task"] as const;

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

export function statusFilterToApiValue(status: string): string {
  if (status === "published") return "true";
  if (status === "unpublished") return "false";
  return "";
}
