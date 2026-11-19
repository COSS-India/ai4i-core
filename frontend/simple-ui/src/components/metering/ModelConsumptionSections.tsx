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
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import React from "react";
import { formatModelTaskTypeLabel } from "../../config/constants";
import { METERING } from "../../config/meteringConstants";
import type { ModelTopN, TopModelRow } from "../../types/metering";
import {
  formatCompactNumber,
  modelConsumptionTaskTypeColor,
  type ModelInsights,
  type ServiceChartSlice,
} from "../../utils/meteringFormatters";
import { normalizeModelTaskType } from "../../utils/meteringTaskType";
import { MeteringEmptyState } from "./MeteringChartPanel";
import MeteringDonutChart, { DonutRankedLayout } from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";
import SegmentedTabBar from "./SegmentedTabBar";

const section = METERING.SECTIONS.MODEL;

interface ModelInsightCardsProps {
  insights: ModelInsights;
  isPlatformWide: boolean;
  showModelCountKpis: boolean;
}

/** Model tab KPI cards: Total / Active Models (optional), Overall Success Rate, Most Used Model. */
export const ModelInsightCards: React.FC<ModelInsightCardsProps> = ({
  insights,
  isPlatformWide,
  showModelCountKpis,
}) => {
  const requestsScope = isPlatformWide
    ? section.REQUESTS_ACROSS_INSTITUTIONS
    : section.REQUESTS_ACROSS_INSTITUTION;
  const mostUsedHelper =
    insights.mostUsedRequests > 0
      ? `${formatCompactNumber(insights.mostUsedRequests, "indian")} ${requestsScope}`
      : undefined;
  const hasMostUsed = insights.mostUsedName !== METERING.GRAPH.EMPTY_VALUE;

  return (
    <SimpleGrid columns={{ base: 1, sm: 2, lg: showModelCountKpis ? 4 : 2 }} spacing={4}>
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
        value={insights.overallSuccessRate?.toFixed(2) ?? METERING.GRAPH.EMPTY_VALUE}
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
              <Tooltip label={insights.mostUsedName} hasArrow placement="top" openDelay={200}>
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
  );
};

interface ModelConsumptionCardProps {
  slices: ServiceChartSlice[];
  topModels: TopModelRow[];
  /** Denominator for the top models' percentages; shown in the donut centre. */
  topModelsTotalRequests?: number;
  topN: ModelTopN;
  onTopNChange: (n: ModelTopN) => void;
  /** Shown in place of the donut and list when there are no slices. */
  emptyMessage: string;
}

/** Model Consumption: donut + ranked top models, with a Top N switch. */
export const ModelConsumptionCard: React.FC<ModelConsumptionCardProps> = ({
  slices,
  topModels,
  topModelsTotalRequests,
  topN,
  onTopNChange,
  emptyMessage,
}) => {
  const isEmpty = slices.length === 0;
  const rankedShare = METERING.SECTIONS.RANKED_SHARE;

  return (
    <MeteringSectionCard
      title={section.TITLE}
      subtitle={section.SUBTITLE}
      sectionLabel
      action={
        isEmpty ? undefined : (
          <SegmentedTabBar
            options={[...METERING.MODEL_TOP_N_SEGMENT_OPTIONS]}
            activeId={String(topN)}
            onChange={(id) => onTopNChange(Number(id) as ModelTopN)}
            justify="flex-end"
          />
        )
      }
    >
      {isEmpty ? (
        // Same height as the donut, so the card doesn't grow when there is no data.
        <MeteringEmptyState height={260} message={emptyMessage} />
      ) : (
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
              total={topModels.length ? topModelsTotalRequests : undefined}
            />
          }
          list={
            <RankedShareList
              rows={topModels.map((row, i) => ({
                rank: row.rank,
                label: row.model_name,
                taskType: row.task_type ?? undefined,
                subtitle: row.task_type ? formatModelTaskTypeLabel(row.task_type) : undefined,
                formattedValue:
                  row.formatted_requests || formatCompactNumber(row.requests, "indian"),
                percentage: row.consumption_pct,
                color: modelConsumptionTaskTypeColor(row.task_type, i),
              }))}
              variant="modelWithTaskType"
              headerLeft={section.TABLE_MODEL}
              headerTaskType={section.TABLE_TASK_TYPE}
              headerTotal={rankedShare.HEADER_TOTAL_REQUESTS}
              headerRight={rankedShare.HEADER_RIGHT}
              tipTotal={rankedShare.TOOLTIPS.TOTAL_REQUESTS}
              tipTaskType={section.TOOLTIPS.TASK_TYPE}
              tipRight={section.TOOLTIPS.CONSUMPTION_PCT}
            />
          }
        />
      )}
    </MeteringSectionCard>
  );
};

interface TaskTypeFilterMenuProps {
  taskTypeNames: string[];
  /** Normalised task type keys that are checked. */
  selectedTaskTypes: Set<string>;
  label: string;
  onToggle: (taskType: string) => void;
}

/** Multi-select Task Type filter for the Model Consumption Drill Down; hidden with no task types. */
export const TaskTypeFilterMenu: React.FC<TaskTypeFilterMenuProps> = ({
  taskTypeNames,
  selectedTaskTypes,
  label,
  onToggle,
}) =>
  taskTypeNames.length === 0 ? null : (
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
            {label}
          </Text>
        </MenuButton>
        <Portal>
          <MenuList maxH="320px" overflowY="auto" zIndex={10}>
            {taskTypeNames.map((taskType) => (
              <MenuItem key={taskType} onClick={() => onToggle(taskType)} closeOnSelect={false}>
                <Checkbox
                  isChecked={selectedTaskTypes.has(normalizeModelTaskType(taskType))}
                  onChange={() => onToggle(taskType)}
                  onClick={(e) => e.stopPropagation()}
                  mr={2}
                />
                {formatModelTaskTypeLabel(taskType)}
              </MenuItem>
            ))}
          </MenuList>
        </Portal>
      </Menu>
    </Box>
  );
