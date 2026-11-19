import {
  MODEL_VERSION,
  MODEL_VERSION_FILTER_LIST,
  formatModelTaskTypeLabel,
  formatModelVersionFilterLabel,
} from "../../config/constants";
import type { DataTableColumnFilters, DataTableFilterDef } from "../common/table";

/** Status and Task type selects above the Model List; values are sent to GET /models/list. */
export function buildModelToolbarFilterDefs(options: Readonly<{
  filters: DataTableColumnFilters;
  setFilter: (id: string, value: string) => void;
  taskTypeNames: readonly string[];
}>): DataTableFilterDef[] {
  const { filters, setFilter, taskTypeNames } = options;
  const showTaskTypeAll = taskTypeNames.length > 1;
  // One enabled task type: show it picked (no All).
  const fallbackTaskType = showTaskTypeAll ? "" : taskTypeNames[0] ?? "";
  return [
    {
      id: "status",
      label: "Status",
      type: "select",
      param: "version_status",
      value: filters.status ?? MODEL_VERSION.FILTER.ALL,
      onChange: (value) => setFilter("status", value),
      options: [
        { label: "All", value: MODEL_VERSION.FILTER.ALL },
        ...MODEL_VERSION_FILTER_LIST.map((s) => ({
          label: formatModelVersionFilterLabel(s),
          value: s,
        })),
      ],
    },
    {
      id: "taskType",
      label: "Task type",
      type: "select",
      param: "task_types",
      value: filters.taskType ?? fallbackTaskType,
      onChange: (value) => setFilter("taskType", value),
      // Fits the longest task type (LANGUAGE-DIARIZATION).
      width: { base: "full", sm: "240px" },
      options: [
        ...(showTaskTypeAll ? [{ label: "All", value: "" }] : []),
        ...taskTypeNames.map((t) => ({
          label: formatModelTaskTypeLabel(t),
          value: t,
        })),
      ],
    },
  ];
}
