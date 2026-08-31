import {
  Box,
  Checkbox,
  HStack,
  SimpleGrid,
  Tbody,
  Td,
  Text,
  Thead,
  Tooltip,
  Tr,
  VStack,
  Wrap,
  WrapItem,
} from "@chakra-ui/react";
import React, { useEffect, useMemo, useState } from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { METERING } from "../../config/meteringConstants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import type { ModelConsumptionResponse, ModelTopN } from "../../types/metering";
import {
  buildModelBreakdownChart,
  buildTaskTypeConsumptionChart,
  buildTopModelsChart,
  deriveModelInsights,
  formatCompactNumber,
  formatNativeConsumption,
  getWindowLabel,
} from "../../utils/meteringFormatters";
import { meteringServiceColor } from "../../utils/meteringColors";
import {
  enrichModelConsumptionRows,
  normalizeModelTaskType,
  taskTypeByModelName,
} from "../../utils/meteringTaskType";
import { useMeteringTableSort } from "../../utils/meteringTableSort";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringDonutChart, { DonutRankedLayout } from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";
import SegmentedTabBar from "./SegmentedTabBar";
import SortableTh from "./SortableTh";
import { TaskTypeLabel } from "./UsageSpendCells";

interface ModelConsumptionTabProps {
  data?: ModelConsumptionResponse;
  isLoading?: boolean;
  errorMessage?: string | null;
  /** When false, Most used helper uses institution-scoped copy. */
  isPlatformWide?: boolean;
}

const ModelConsumptionTab: React.FC<ModelConsumptionTabProps> = ({
  data,
  isLoading,
  errorMessage,
  isPlatformWide = true,
}) => {
  const section = METERING.SECTIONS.MODEL;
  const { taskTypeNames } = useInferenceTypes();
  const [topN, setTopN] = useState<ModelTopN>(METERING.MODEL_TOP_N_DEFAULT);
  const [selectedTaskTypes, setSelectedTaskTypes] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (taskTypeNames.length > 0) {
      setSelectedTaskTypes(new Set(taskTypeNames.map(normalizeModelTaskType)));
    }
  }, [taskTypeNames]);

  const breakdown = data?.breakdown ?? [];
  const topModels = data?.top_models ?? [];

  const enrichedBreakdown = useMemo(
    () => enrichModelConsumptionRows(breakdown),
    [breakdown],
  );

  const allTaskTypesSelected =
    taskTypeNames.length === 0 ||
    selectedTaskTypes.size === 0 ||
    selectedTaskTypes.size >= taskTypeNames.length;

  const filteredBreakdown = useMemo(() => {
    if (allTaskTypesSelected) return enrichedBreakdown;
    return enrichedBreakdown.filter((row) =>
      selectedTaskTypes.has(normalizeModelTaskType(row.task_type)),
    );
  }, [enrichedBreakdown, selectedTaskTypes, allTaskTypesSelected]);

  const modelTaskTypeMap = useMemo(
    () => taskTypeByModelName(enrichedBreakdown),
    [enrichedBreakdown],
  );

  const visibleTopModels = useMemo(() => {
    const sliced = topModels.slice(0, topN);
    if (allTaskTypesSelected) return sliced;
    return sliced.filter((row) => {
      const tt = modelTaskTypeMap.get(row.model_name.trim());
      return tt ? selectedTaskTypes.has(normalizeModelTaskType(tt)) : false;
    });
  }, [topModels, topN, allTaskTypesSelected, selectedTaskTypes, modelTaskTypeMap]);

  const { slices } = useMemo(() => {
    if (visibleTopModels.length) return buildTopModelsChart(visibleTopModels);
    return buildModelBreakdownChart(filteredBreakdown);
  }, [visibleTopModels, filteredBreakdown]);

  const insights = useMemo(
    () => deriveModelInsights(data?.summary, filteredBreakdown),
    [data?.summary, filteredBreakdown],
  );

  const taskTypeChart = useMemo(
    () => buildTaskTypeConsumptionChart(filteredBreakdown),
    [filteredBreakdown],
  );

  const sortAccessors = useMemo(
    () => ({
      task_type: (row: (typeof filteredBreakdown)[number]) =>
        formatModelTaskTypeLabel(row.task_type),
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

  const { sortedRows, sortKey, sortDirection, toggleSort } = useMeteringTableSort(
    filteredBreakdown,
    "requests",
    sortAccessors,
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

  const mostUsedHelper =
    insights && insights.mostUsedRequests > 0
      ? `${formatCompactNumber(insights.mostUsedRequests, "indian")} ${
          isPlatformWide
            ? section.REQUESTS_ACROSS_INSTITUTIONS
            : section.REQUESTS_ACROSS_INSTITUTION
        }`
      : undefined;

  const hasMostUsed = Boolean(
    insights && insights.mostUsedName !== METERING.GRAPH.EMPTY_VALUE,
  );

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!data}
      errorMessage={errorMessage}
      emptyMessage={METERING.EMPTY.MODEL_CONSUMPTION}
    >
      {data ? (
        <VStack align="stretch" spacing={6}>
          {insights ? (
            <SimpleGrid columns={{ base: 1, sm: 2 }} spacing={4}>
              <KpiCard
                label={section.OVERALL_SUCCESS}
                value={
                  insights.overallSuccessRate != null
                    ? insights.overallSuccessRate.toFixed(2)
                    : METERING.GRAPH.EMPTY_VALUE
                }
                helper={section.SUCCESS_RATE_SUFFIX}
                tooltip={section.TOOLTIPS.OVERALL_SUCCESS}
                valueColor="green.600"
              />
              <KpiCard
                label={section.MOST_USED}
                valueFontSize="xl"
                value={
                  hasMostUsed ? (
                    <HStack spacing={2} minW={0} w="full">
                      <Box w={2} h={2} borderRadius="full" bg="green.400" flexShrink={0} />
                      <Tooltip
                        label={insights.mostUsedName}
                        hasArrow
                        placement="top"
                        openDelay={200}
                      >
                        <Text noOfLines={1}>{insights.mostUsedName}</Text>
                      </Tooltip>
                    </HStack>
                  ) : (
                    METERING.GRAPH.EMPTY_VALUE
                  )
                }
                helper={mostUsedHelper}
                tooltip={section.TOOLTIPS.MOST_USED}
                valueColor="gray.800"
              />
            </SimpleGrid>
          ) : null}

          {taskTypeChart.slices.length > 0 ? (
            <MeteringSectionCard
              title={section.TASK_TYPE_DONUT_TITLE}
              subtitle={section.TASK_TYPE_DONUT_SUBTITLE}
              sectionLabel
            >
              <DonutRankedLayout
                chart={
                  <MeteringDonutChart
                    data={taskTypeChart.slices.map(({ name, value, color }) => ({
                      name,
                      value,
                      color,
                    }))}
                    height={260}
                    innerRadius={65}
                    outerRadius={100}
                    showTooltip
                    centerPrimary={section.TASK_TYPE_DONUT_PRIMARY}
                    centerSecondary={section.TASK_TYPE_DONUT_SECONDARY}
                    total={taskTypeChart.totalRequests}
                  />
                }
                list={
                  <RankedShareList
                    rows={taskTypeChart.slices.map((slice, i) => ({
                      rank: i + 1,
                      label: slice.name,
                      formattedValue: formatCompactNumber(slice.value, "indian"),
                      percentage: slice.pct,
                    }))}
                    headerLeft={section.TABLE_TASK_TYPE}
                    headerTotal={METERING.SECTIONS.RANKED_SHARE.HEADER_TOTAL_REQUESTS}
                    headerRight={METERING.SECTIONS.RANKED_SHARE.HEADER_RIGHT}
                    tipTotal={METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.TOTAL_REQUESTS}
                    tipRight={METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.PCT_OF_TOTAL}
                  />
                }
              />
            </MeteringSectionCard>
          ) : null}

          <MeteringSectionCard
            title={section.TITLE}
            subtitle={section.SUBTITLE}
            sectionLabel
            action={
              <SegmentedTabBar
                options={[...METERING.MODEL_TOP_N_SEGMENT_OPTIONS]}
                activeId={String(topN)}
                onChange={(id) => setTopN(Number(id) as ModelTopN)}
                justify="flex-end"
              />
            }
          >
            <DonutRankedLayout
              chart={
                <MeteringDonutChart
                  data={slices.map(({ name, value, color }) => ({ name, value, color }))}
                  height={260}
                  innerRadius={65}
                  outerRadius={100}
                  showTooltip
                  centerPrimary={section.DONUT_PRIMARY}
                  centerSecondary={section.DONUT_SECONDARY}
                  total={
                    visibleTopModels.length
                      ? data.top_models_total_requests
                      : undefined
                  }
                />
              }
              list={
                <RankedShareList
                  rows={visibleTopModels.map((row) => ({
                    rank: row.rank,
                    label: row.model_name,
                    subtitle: modelTaskTypeMap.get(row.model_name.trim())
                      ? formatModelTaskTypeLabel(
                          modelTaskTypeMap.get(row.model_name.trim())!,
                        )
                      : undefined,
                    formattedValue:
                      row.formatted_requests ||
                      formatCompactNumber(row.requests, "indian"),
                    percentage: row.consumption_pct,
                  }))}
                  headerLeft="Model"
                  headerTaskType={section.TABLE_TASK_TYPE}
                  headerTotal={METERING.SECTIONS.RANKED_SHARE.HEADER_TOTAL_REQUESTS}
                  headerRight={METERING.SECTIONS.RANKED_SHARE.HEADER_RIGHT}
                  tipTotal={METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.TOTAL_REQUESTS}
                  tipRight={section.TOOLTIPS.CONSUMPTION_PCT}
                />
              }
            />
          </MeteringSectionCard>

          <MeteringSectionCard
            title={section.BREAKDOWN_TITLE}
            subtitle={`${section.BREAKDOWN_SUBTITLE_PREFIX} ${getWindowLabel(data.scope.window)}`}
            sectionLabel
            bare
          >
            {taskTypeNames.length > 0 ? (
              <Box mb={4}>
                <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                  {section.FILTER_TASK_TYPES}
                </Text>
                <Wrap spacing={3}>
                  {taskTypeNames.map((taskType) => {
                    const key = normalizeModelTaskType(taskType);
                    const checked = selectedTaskTypes.has(key);
                    return (
                      <WrapItem key={taskType}>
                        <Checkbox
                          size="sm"
                          isChecked={checked}
                          onChange={() => toggleTaskType(taskType)}
                        >
                          {formatModelTaskTypeLabel(taskType)}
                        </Checkbox>
                      </WrapItem>
                    );
                  })}
                </Wrap>
              </Box>
            ) : null}

            <MeteringDataTable>
              <Thead bg="gray.50">
                <Tr>
                  <SortableTh
                    sortKey="task_type"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                    message={section.TOOLTIPS.TASK_TYPE}
                  >
                    {section.TABLE_TASK_TYPE}
                  </SortableTh>
                  <SortableTh
                    sortKey="model_name"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                  >
                    {section.TABLE_MODEL}
                  </SortableTh>
                  <SortableTh
                    sortKey="name"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                  >
                    {section.TABLE_SERVICE}
                  </SortableTh>
                  <SortableTh
                    sortKey="requests"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                    message={section.TOOLTIPS.TOTAL_REQUESTS}
                    isNumeric
                  >
                    {section.TABLE_TOTAL_REQUESTS}
                  </SortableTh>
                  <SortableTh
                    sortKey="native_units"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                    message={section.TOOLTIPS.TOKEN_CONSUMPTION}
                    isNumeric
                  >
                    {section.TABLE_NATIVE}
                  </SortableTh>
                  <SortableTh
                    sortKey="success_pct"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                    message={section.TOOLTIPS.SUCCESS_RATE}
                    isNumeric
                  >
                    {section.TABLE_SUCCESS}
                  </SortableTh>
                  <SortableTh
                    sortKey="failure_rate_pct"
                    activeSortKey={sortKey}
                    sortDirection={sortDirection}
                    onSort={toggleSort}
                    message={section.TOOLTIPS.FAILURE_RATE}
                    isNumeric
                  >
                    {section.TABLE_FAILURE}
                  </SortableTh>
                </Tr>
              </Thead>
              <Tbody>
                {sortedRows.map((row, i) => (
                  <Tr key={`${row.service_id}-${row.model_name ?? i}`}>
                    <Td fontSize="sm">
                      {row.task_type ? (
                        <TaskTypeLabel
                          taskType={row.task_type}
                          color={meteringServiceColor(row.name, i)}
                        />
                      ) : (
                        METERING.GRAPH.EMPTY_VALUE
                      )}
                    </Td>
                    <Td fontSize="sm" color="gray.800" fontWeight="medium">
                      {row.model_name?.trim() || METERING.GRAPH.EMPTY_VALUE}
                    </Td>
                    <Td>
                      <HStack spacing={2}>
                        <Box
                          w={1}
                          h={5}
                          borderRadius="sm"
                          bg={meteringServiceColor(row.name, i)}
                        />
                        <Text fontWeight="medium" fontSize="sm">
                          {row.name}
                        </Text>
                      </HStack>
                    </Td>
                    <Td isNumeric fontSize="sm">
                      {formatCompactNumber(row.requests, "indian")}
                    </Td>
                    <Td isNumeric fontSize="sm" color="gray.600">
                      {formatNativeConsumption(row.native_units, row.native_unit_suffix)}
                    </Td>
                    <Td isNumeric fontSize="sm" color="green.600" fontWeight="medium">
                      {row.success_pct.toFixed(2)}
                    </Td>
                    <Td isNumeric fontSize="sm" color="red.500" fontWeight="medium">
                      {row.failure_rate_pct.toFixed(2)}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </MeteringDataTable>
          </MeteringSectionCard>
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default ModelConsumptionTab;
