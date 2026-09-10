/**
 * Single import path for all app tables.
 *
 * ```tsx
 * import DataTable, {
 *   type DataTableColumn,
 *   createActionsColumn,
 *   FieldLabel,
 * } from "@/components/common/table";
 * ```
 */
export {
  DataTable as default,
  DataTable,
  DATA_TABLE_HEADER_SX,
  DATA_TABLE_CELL_MAX_W,
  TableSearchField,
  TableSelectField,
  type DataTableColumn,
  type DataTableProps,
  type DataTableLayout,
  type DataTableCardProps,
  type DataTableAdminProps,
  type DataTableSearchConfig,
  type DataTableFilterDef,
  type DataTableFilterOption,
  type DataTableSortState,
  type DataTableSortDirection,
} from "./DataTable";

export { DataTableShell } from "./dataTableUtils";

export {
  DataTableActions,
  createActionsColumn,
  type DataTableAction,
  type DataTableActionId,
  type DataTableActionsProps,
  type CreateActionsColumnOptions,
} from "./DataTableActions";

export { default as FieldLabel, type FieldLabelProps, type FieldLabelVariant } from "./FieldLabel";

export { TablePaginationBar } from "./TableControls";

export {
  DEFAULT_PAGE_SIZE_OPTIONS,
  useAdminDataTable,
  useAdminDataTableServer,
  type UseAdminDataTableServerOptions,
} from "../../hooks/useAdminDataTable";
