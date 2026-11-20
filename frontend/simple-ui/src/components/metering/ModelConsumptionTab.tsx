import {
  HStack,
  IconButton,
  Text,
  VStack,
} from "@chakra-ui/react";
import { ChevronRightIcon } from "@chakra-ui/icons";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { METERING } from "../../config/meteringConstants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import type {
  ModelConsumptionResponse,
  ModelConsumptionRow,
  ModelTopN,
} from "../../types/metering";
import {
  buildModelBreakdownChart,
  buildTopModelsChart,
  deriveModelInsights,
  formatCompactNumber,
  formatModelNativeUnits,
  formatPercent,
  getScopePeriodLabel,
  modelConsumptionTaskTypeColor,
} from "../../utils/meteringFormatters";
import { normalizeModelTaskType } from "../../utils/meteringTaskType";
import DataTable, { type DataTableColumn } from "../common/table";
import { sortHeaderTrailingWidthPx } from "../common/TableControls";
import MeteringAsyncState from "./MeteringAsyncState";
import { MeteringEmptyState } from "./MeteringChartPanel";
import {
  ModelConsumptionCard,
  ModelInsightCards,
  TaskTypeFilterMenu,
} from "./ModelConsumptionSections";
import MeteringSectionCard from "./MeteringSectionCard";
import { ModelTokenBreakdownRows } from "./ModelTokenBreakdownRows";
import { TaskTypeLabel } from "./UsageSpendCells";

const breakdownRowKey = (row: ModelConsumptionRow) =>
  `${row.service_id}-${row.model_name ?? row.name}`;

/**
 * Fixed table layout gives every column without a width an equal share, so
 * "LLM" would get as much room as a long service name. Task Type and the
 * numeric columns get fixed widths; Model Name and Service Name share the rest.
 *
 * The numeric widths fit the whole header on one line (text + info and sort
 * icons + cell padding; a wrapped header next to one-line ones looks broken)
 * and its widest value ("1,23,45,678 tokens", "100.0%") plus the icon inset
 * its cells use (see NUMERIC_TEXT_PROPS). Re-check these if a header is renamed.
 *
 * Total Requests, Successful and Failed share one width so their values sit at
 * even intervals. 190px is the floor: "TOTAL REQUESTS" + icons + padding
 * measures ~180px, and anything narrower wraps it onto two lines.
 */
const NUMERIC_COLUMN_PX = 190;
const TASK_TYPE_COLUMN_PX = 160;
// "TOTAL NATIVE UNITS" + icons + padding measures ~196px; the widest value
// ("1,23,45,678 chars" + inset) about the same.
const NATIVE_UNITS_COLUMN_PX = 210;
/** Narrowest Model Name / Service Name may get before the table scrolls instead. */
const NAME_COLUMN_MIN_PX = 150;

const COLUMN_WIDTHS = {
  task_type: `${TASK_TYPE_COLUMN_PX}px`,
  model_name: undefined,
  name: undefined,
  requests: `${NUMERIC_COLUMN_PX}px`,
  success_pct: `${NUMERIC_COLUMN_PX}px`,
  failure_rate_pct: `${NUMERIC_COLUMN_PX}px`,
  native_units: `${NATIVE_UNITS_COLUMN_PX}px`,
} as const;

/**
 * Below this width (1240px) the table scrolls sideways rather than squeezing
 * the name columns to an ellipsis, or clipping Total Native Units off the card:
 * all fixed columns plus both name columns at their minimum.
 */
const TABLE_MIN_WIDTH = `${
  TASK_TYPE_COLUMN_PX + 3 * NUMERIC_COLUMN_PX + NATIVE_UNITS_COLUMN_PX + 2 * NAME_COLUMN_MIN_PX
}px`;

/**
 * Numeric cells: right-aligned (set per column) with equal-width digits, so
 * units, tenths and decimal points line up down the column.
 */
const NUMERIC_TEXT_PROPS = {
  fontSize: "sm",
  // Values end under the header text, not under its info + sort icons.
  pr: `${sortHeaderTrailingWidthPx(true)}px`,
  whiteSpace: "nowrap",
  // Not a Chakra style prop, so it goes through sx.
  sx: { fontVariantNumeric: "tabular-nums" },
} as const;

/** LLM rows carry a token breakdown and can be expanded to show it. */
const hasTokenBreakdown = (row: ModelConsumptionRow) =>
  (row.native_breakdown?.length ?? 0) > 0;

/*
 * Cell renderers live at module level (not inline in the column definitions)
 * so they are not re-created on every render of the tab.
 */

/** Expand toggle (LLM rows only) + task type label. */
function renderTaskTypeCell(
  row: ModelConsumptionRow,
  index: number,
  isOpen: boolean,
  onToggle: (key: string) => void,
): React.ReactNode {
  const key = breakdownRowKey(row);
  return (
    <HStack spacing={1}>
      <IconButton
        aria-label={`${METERING.SECTIONS.MODEL.TOGGLE_TOKEN_BREAKDOWN} ${row.name}`}
        aria-expanded={isOpen}
        icon={<ChevronRightIcon />}
        size="xs"
        variant="ghost"
        visibility={hasTokenBreakdown(row) ? "visible" : "hidden"}
        transform={isOpen ? "rotate(90deg)" : undefined}
        transition="transform 0.15s ease"
        onClick={(event) => {
          event.stopPropagation();
          onToggle(key);
        }}
      />
      {row.task_type ? (
        <TaskTypeLabel
          taskType={row.task_type}
          color={modelConsumptionTaskTypeColor(row.task_type, index)}
        />
      ) : (
        <Text fontSize="sm">{METERING.GRAPH.EMPTY_VALUE}</Text>
      )}
    </HStack>
  );
}

function renderModelNameCell(row: ModelConsumptionRow): React.ReactNode {
  return (
    <Text fontSize="sm" color="gray.800" fontWeight="medium">
      {row.model_name?.trim() || METERING.GRAPH.EMPTY_VALUE}
    </Text>
  );
}

function renderServiceNameCell(row: ModelConsumptionRow): React.ReactNode {
  return (
    <Text fontWeight="medium" fontSize="sm">
      {row.name}
    </Text>
  );
}

function renderRequestsCell(row: ModelConsumptionRow): React.ReactNode {
  return <Text {...NUMERIC_TEXT_PROPS}>{formatCompactNumber(row.requests, "indian")}</Text>;
}

function renderSuccessCell(row: ModelConsumptionRow): React.ReactNode {
  return (
    <Text {...NUMERIC_TEXT_PROPS} color="green.600" fontWeight="medium">
      {formatPercent(row.success_pct)}
    </Text>
  );
}

function renderFailureCell(row: ModelConsumptionRow): React.ReactNode {
  return (
    <Text {...NUMERIC_TEXT_PROPS} color="red.500" fontWeight="medium">
      {formatPercent(row.failure_rate_pct)}
    </Text>
  );
}

/**
 * "267", not "267 tokens" (as the story asks); other units are kept
 * ("19 chars", "4 min") so non-LLM rows still say what they count.
 */
function renderNativeUnitsCell(row: ModelConsumptionRow): React.ReactNode {
  return (
    <Text {...NUMERIC_TEXT_PROPS} color="gray.600">
      {formatModelNativeUnits(row.native_units, row.native_unit_suffix)}
    </Text>
  );
}

interface ModelConsumptionTabProps {
  data?: ModelConsumptionResponse;
  isLoading?: boolean;
  errorMessage?: string | null;
  /** When false, Most used helper uses institution-scoped copy. */
  isPlatformWide?: boolean;
  showModelCountKpis?: boolean;
}

const ModelConsumptionTab: React.FC<ModelConsumptionTabProps> = ({
  data,
  isLoading,
  errorMessage,
  isPlatformWide = true,
  showModelCountKpis = true,
}) => {
  const section = METERING.SECTIONS.MODEL;
  const { taskTypeNames } = useInferenceTypes();
  const [topN, setTopN] = useState<ModelTopN>(METERING.MODEL_TOP_N_DEFAULT);
  const [selectedTaskTypes, setSelectedTaskTypes] = useState<Set<string>>(new Set());
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = useCallback((key: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  useEffect(() => {
    if (taskTypeNames.length > 0) {
      setSelectedTaskTypes(new Set(taskTypeNames.map(normalizeModelTaskType)));
    }
  }, [taskTypeNames]);

  const breakdown = data?.breakdown ?? [];
  const topModels = data?.top_models ?? [];

  const allTaskTypesSelected =
    taskTypeNames.length === 0 ||
    selectedTaskTypes.size >= taskTypeNames.length;

  const filteredBreakdown = useMemo(() => {
    if (allTaskTypesSelected) return breakdown;
    return breakdown.filter(
      (row) =>
        row.task_type &&
        selectedTaskTypes.has(normalizeModelTaskType(row.task_type)),
    );
  }, [breakdown, selectedTaskTypes, allTaskTypesSelected]);

  const visibleTopModels = useMemo(() => {
    const filtered = allTaskTypesSelected
      ? topModels
      : topModels.filter((row) =>
          row.task_type
            ? selectedTaskTypes.has(normalizeModelTaskType(row.task_type))
            : false,
        );
    return filtered.slice(0, topN);
  }, [topModels, topN, allTaskTypesSelected, selectedTaskTypes]);

  const { slices } = useMemo(() => {
    if (visibleTopModels.length) return buildTopModelsChart(visibleTopModels);
    return buildModelBreakdownChart(filteredBreakdown);
  }, [visibleTopModels, filteredBreakdown]);

  const insights = useMemo(
    () => deriveModelInsights(data?.summary, filteredBreakdown),
    [data?.summary, filteredBreakdown],
  );

  const taskTypeFilterLabel = useMemo(() => {
    if (allTaskTypesSelected) return "All task types";
    if (selectedTaskTypes.size === 0) return "No task types selected";
    if (selectedTaskTypes.size === 1) {
      const only = taskTypeNames.find((taskType) =>
        selectedTaskTypes.has(normalizeModelTaskType(taskType)),
      );
      return only ? formatModelTaskTypeLabel(only) : "1 selected";
    }
    return `${selectedTaskTypes.size} task types selected`;
  }, [allTaskTypesSelected, selectedTaskTypes, taskTypeNames]);

  const sortAccessors = useMemo(
    () => ({
      task_type: (row: (typeof filteredBreakdown)[number]) =>
        row.task_type ? formatModelTaskTypeLabel(row.task_type) : "",
      model_name: (row: (typeof filteredBreakdown)[number]) =>
        row.model_name?.trim() || "",
      name: (row: (typeof filteredBreakdown)[number]) => row.name,
      requests: (row: (typeof filteredBreakdown)[number]) => row.requests,
      native_units: (row: (typeof filteredBreakdown)[number]) => row.native_units,
      success_pct: (row: (typeof filteredBreakdown)[number]) => row.success_pct,
      failure_rate_pct: (row: (typeof filteredBreakdown)[number]) =>
        row.failure_rate_pct,
    }),
    [],
  );

  type BreakdownRow = (typeof filteredBreakdown)[number];

  const breakdownColumns = useMemo<DataTableColumn<BreakdownRow>[]>(
    () => [
      {
        id: "task_type",
        header: section.TABLE_TASK_TYPE,
        hint: section.TOOLTIPS.TASK_TYPE,
        wrapHeader: true,
        width: COLUMN_WIDTHS.task_type,
        cell: (row, i) =>
          renderTaskTypeCell(row, i, expandedRows.has(breakdownRowKey(row)), toggleRow),
      },
      {
        id: "model_name",
        header: section.TABLE_MODEL,
        hint: section.TOOLTIPS.MODEL_NAME,
        wrapHeader: true,
        width: COLUMN_WIDTHS.model_name,
        sortable: true,
        sortAccessor: sortAccessors.model_name,
        cell: renderModelNameCell,
      },
      {
        id: "name",
        header: section.TABLE_SERVICE,
        hint: section.TOOLTIPS.SERVICE_NAME,
        wrapHeader: true,
        width: COLUMN_WIDTHS.name,
        sortable: true,
        sortAccessor: sortAccessors.name,
        cell: renderServiceNameCell,
      },
      // Request counts and their success / failure split sit together; native
      // units come last. ModelTokenBreakdownRows mirrors this order.
      {
        id: "requests",
        header: section.TABLE_TOTAL_REQUESTS,
        sortable: true,
        sortAccessor: sortAccessors.requests,
        hint: section.TOOLTIPS.TOTAL_REQUESTS,
        wrapHeader: true,
        width: COLUMN_WIDTHS.requests,
        align: "right",
        cell: renderRequestsCell,
      },
      {
        id: "success_pct",
        header: section.TABLE_SUCCESS,
        sortable: true,
        sortAccessor: sortAccessors.success_pct,
        hint: section.TOOLTIPS.SUCCESS_RATE,
        wrapHeader: true,
        width: COLUMN_WIDTHS.success_pct,
        align: "right",
        cell: renderSuccessCell,
      },
      {
        id: "failure_rate_pct",
        header: section.TABLE_FAILURE,
        sortable: true,
        sortAccessor: sortAccessors.failure_rate_pct,
        hint: section.TOOLTIPS.FAILURE_RATE,
        wrapHeader: true,
        width: COLUMN_WIDTHS.failure_rate_pct,
        align: "right",
        cell: renderFailureCell,
      },
      {
        id: "native_units",
        header: section.TABLE_NATIVE,
        sortable: true,
        sortAccessor: sortAccessors.native_units,
        hint: section.TOOLTIPS.TOKEN_CONSUMPTION,
        wrapHeader: true,
        width: COLUMN_WIDTHS.native_units,
        align: "right",
        cell: renderNativeUnitsCell,
      },
    ],
    [section, sortAccessors, expandedRows, toggleRow],
  );

  const renderTokenBreakdown = useCallback(
    (row: BreakdownRow) =>
      hasTokenBreakdown(row) && expandedRows.has(breakdownRowKey(row)) ? (
        <ModelTokenBreakdownRows row={row} />
      ) : null,
    [expandedRows],
  );

  const toggleTaskType = (taskType: string) => {
    const key = normalizeModelTaskType(taskType);
    setSelectedTaskTypes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectAllTaskTypes = useCallback(() => {
    setSelectedTaskTypes(new Set(taskTypeNames.map(normalizeModelTaskType)));
  }, [taskTypeNames]);

  const clearAllTaskTypes = useCallback(() => {
    setSelectedTaskTypes(new Set());
  }, []);

  // No usage at all in the window, vs usage that the Task Type filter hides.
  const hasNoUsage = breakdown.length === 0 && topModels.length === 0;
  const tableEmptyMessage =
    breakdown.length > 0 ? METERING.EMPTY.FILTERED : METERING.EMPTY.PERIOD;

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!data}
      errorMessage={errorMessage}
      emptyMessage={METERING.EMPTY.PERIOD}
    >
      {data ? (
        <VStack align="stretch" spacing={6}>
          {insights ? (
            <ModelInsightCards
              insights={insights}
              isPlatformWide={isPlatformWide}
              showModelCountKpis={showModelCountKpis}
            />
          ) : null}

          <ModelConsumptionCard
            slices={slices}
            topModels={visibleTopModels}
            topModelsTotalRequests={data.top_models_total_requests}
            topN={topN}
            onTopNChange={setTopN}
            emptyMessage={hasNoUsage ? METERING.EMPTY.PERIOD : METERING.EMPTY.FILTERED}
          />

          <MeteringSectionCard
            title={section.BREAKDOWN_TITLE}
            subtitle={`${section.BREAKDOWN_SUBTITLE_PREFIX} ${getScopePeriodLabel(data.scope)}`}
            sectionLabel
            bare
          >
            {/* Nothing to filter or list: one empty state instead of the filter and an empty table. */}
            {hasNoUsage ? (
              <MeteringEmptyState height={260} />
            ) : (
              <>
                <TaskTypeFilterMenu
                  taskTypeNames={taskTypeNames}
                  selectedTaskTypes={selectedTaskTypes}
                  label={taskTypeFilterLabel}
                  onToggle={toggleTaskType}
                  onSelectAll={selectAllTaskTypes}
                  onClearAll={clearAllTaskTypes}
                />
                <DataTable
                  columns={breakdownColumns}
                  rows={filteredBreakdown}
                  rowKey={breakdownRowKey}
                  defaultSortKey="requests"
                  defaultSortDirection="desc"
                  theadBg="gray.50"
                  containerMt={0}
                  tableMinWidth={TABLE_MIN_WIDTH}
                  scrollX
                  isEmpty={filteredBreakdown.length === 0}
                  emptyMessage={tableEmptyMessage}
                  renderAfterRow={renderTokenBreakdown}
                />
              </>
            )}
          </MeteringSectionCard>
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default ModelConsumptionTab;
