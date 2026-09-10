import {
  Box,
  Button,
  Checkbox,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Portal,
  SimpleGrid,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import React, { useEffect, useMemo, useState } from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { METERING } from "../../config/meteringConstants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import type { ModelConsumptionResponse, ModelTopN } from "../../types/metering";
import {
  buildModelBreakdownChart,
  buildTopModelsChart,
  deriveModelInsights,
  formatCompactNumber,
  formatNativeConsumption,
  getWindowLabel,
  modelConsumptionTaskTypeColor,
} from "../../utils/meteringFormatters";
import { normalizeModelTaskType } from "../../utils/meteringTaskType";
import DataTable, { type DataTableColumn } from "../common/table";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDonutChart, { DonutRankedLayout } from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";
import SegmentedTabBar from "./SegmentedTabBar";
import { TaskTypeLabel } from "./UsageSpendCells";

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
    if (allTaskTypesSelected) return "All model task types";
    if (selectedTaskTypes.size === 0) return "No model task types selected";
    if (selectedTaskTypes.size === 1) {
      const only = taskTypeNames.find((taskType) =>
        selectedTaskTypes.has(normalizeModelTaskType(taskType)),
      );
      return only ? formatModelTaskTypeLabel(only) : "1 selected";
    }
    return `${selectedTaskTypes.size} model task types selected`;
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
        sortable: true,
        sortAccessor: sortAccessors.task_type,
        hint: section.TOOLTIPS.TASK_TYPE,
        cell: (row, i) =>
          row.task_type ? (
            <TaskTypeLabel
              taskType={row.task_type}
              color={modelConsumptionTaskTypeColor(row.task_type, i)}
            />
          ) : (
            METERING.GRAPH.EMPTY_VALUE
          ),
      },
      {
        id: "model_name",
        header: section.TABLE_MODEL,
        sortable: true,
        sortAccessor: sortAccessors.model_name,
        cell: (row) => (
          <Text fontSize="sm" color="gray.800" fontWeight="medium">
            {row.model_name?.trim() || METERING.GRAPH.EMPTY_VALUE}
          </Text>
        ),
      },
      {
        id: "name",
        header: section.TABLE_SERVICE,
        sortable: true,
        sortAccessor: sortAccessors.name,
        cell: (row, i) => {
          const rowColor = modelConsumptionTaskTypeColor(row.task_type, i);
          return (
            <HStack spacing={2}>
              <Box w={1} h={5} borderRadius="sm" bg={rowColor} />
              <Text fontWeight="medium" fontSize="sm">
                {row.name}
              </Text>
            </HStack>
          );
        },
      },
      {
        id: "requests",
        header: section.TABLE_TOTAL_REQUESTS,
        sortable: true,
        sortAccessor: sortAccessors.requests,
        hint: section.TOOLTIPS.TOTAL_REQUESTS,
        isNumeric: true,
        cell: (row) => (
          <Text fontSize="sm">{formatCompactNumber(row.requests, "indian")}</Text>
        ),
      },
      {
        id: "native_units",
        header: section.TABLE_NATIVE,
        sortable: true,
        sortAccessor: sortAccessors.native_units,
        hint: section.TOOLTIPS.TOKEN_CONSUMPTION,
        isNumeric: true,
        cell: (row) => (
          <Text fontSize="sm" color="gray.600">
            {formatNativeConsumption(row.native_units, row.native_unit_suffix)}
          </Text>
        ),
      },
      {
        id: "success_pct",
        header: section.TABLE_SUCCESS,
        sortable: true,
        sortAccessor: sortAccessors.success_pct,
        hint: section.TOOLTIPS.SUCCESS_RATE,
        isNumeric: true,
        cell: (row) => (
          <Text fontSize="sm" color="green.600" fontWeight="medium">
            {row.success_pct.toFixed(2)}
          </Text>
        ),
      },
      {
        id: "failure_rate_pct",
        header: section.TABLE_FAILURE,
        sortable: true,
        sortAccessor: sortAccessors.failure_rate_pct,
        hint: section.TOOLTIPS.FAILURE_RATE,
        isNumeric: true,
        cell: (row) => (
          <Text fontSize="sm" color="red.500" fontWeight="medium">
            {row.failure_rate_pct.toFixed(2)}
          </Text>
        ),
      },
    ],
    [section, sortAccessors],
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
            <SimpleGrid
              columns={{ base: 1, sm: 2, lg: showModelCountKpis ? 4 : 2 }}
              spacing={4}
            >
              {showModelCountKpis ? (
                <>
                  <KpiCard
                    label={section.TOTAL_MODELS}
                    value={insights.totalModels ?? METERING.GRAPH.EMPTY_VALUE}
                    tooltip={section.TOOLTIPS.TOTAL_MODELS}
                    valueColor="gray.800"
                  />
                  <KpiCard
                    label={section.ACTIVE_MODELS}
                    value={insights.activeModels ?? METERING.GRAPH.EMPTY_VALUE}
                    tooltip={section.TOOLTIPS.ACTIVE_MODELS}
                    valueColor="gray.800"
                  />
                </>
              ) : null}
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
                  rows={visibleTopModels.map((row, i) => ({
                    rank: row.rank,
                    label: row.model_name,
                    taskType: row.task_type ?? undefined,
                    subtitle: row.task_type
                      ? formatModelTaskTypeLabel(row.task_type)
                      : undefined,
                    formattedValue:
                      row.formatted_requests ||
                      formatCompactNumber(row.requests, "indian"),
                    percentage: row.consumption_pct,
                    color: modelConsumptionTaskTypeColor(row.task_type, i),
                  }))}
                  variant="modelWithTaskType"
                  headerLeft={section.TABLE_MODEL}
                  headerTaskType={section.TABLE_TASK_TYPE}
                  headerTotal={METERING.SECTIONS.RANKED_SHARE.HEADER_TOTAL_REQUESTS}
                  headerRight={METERING.SECTIONS.RANKED_SHARE.HEADER_RIGHT}
                  tipTotal={METERING.SECTIONS.RANKED_SHARE.TOOLTIPS.TOTAL_REQUESTS}
                  tipTaskType={section.TOOLTIPS.TASK_TYPE}
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
              <Box mb={4} maxW={{ base: "full", sm: "320px" }}>
                <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                  {section.FILTER_TASK_TYPES}
                </Text>
                <Menu closeOnSelect={false} matchWidth>
                  <MenuButton
                    as={Button}
                    rightIcon={<ChevronDownIcon />}
                    w="full"
                    textAlign="left"
                    fontWeight="normal"
                    variant="outline"
                    colorScheme="gray"
                    color="gray.800"
                    bg="white"
                    size="sm"
                    justifyContent="space-between"
                  >
                    <Text as="span" isTruncated display="block" minW={0}>
                      {taskTypeFilterLabel}
                    </Text>
                  </MenuButton>
                  <Portal>
                    <MenuList maxH="320px" overflowY="auto" zIndex={10}>
                      {taskTypeNames.map((taskType) => {
                        const key = normalizeModelTaskType(taskType);
                        const checked = selectedTaskTypes.has(key);
                        return (
                          <MenuItem
                            key={taskType}
                            onClick={() => toggleTaskType(taskType)}
                            closeOnSelect={false}
                          >
                            <Checkbox
                              isChecked={checked}
                              onChange={() => toggleTaskType(taskType)}
                              onClick={(e) => e.stopPropagation()}
                              mr={2}
                            />
                            {formatModelTaskTypeLabel(taskType)}
                          </MenuItem>
                        );
                      })}
                    </MenuList>
                  </Portal>
                </Menu>
              </Box>
            ) : null}

            <DataTable
              columns={breakdownColumns}
              rows={filteredBreakdown}
              rowKey={(row) => `${row.service_id}-${row.model_name ?? row.name}`}
              defaultSortKey="requests"
              defaultSortDirection="desc"
              theadBg="gray.50"
              containerMt={0}
              showAsyncState={false}
            />
          </MeteringSectionCard>
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default ModelConsumptionTab;
