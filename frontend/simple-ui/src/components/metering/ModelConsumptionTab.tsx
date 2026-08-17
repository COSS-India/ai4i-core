import {
  Box,
  HStack,
  SimpleGrid,
  Tbody,
  Td,
  Text,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import { METERING } from "../../config/meteringConstants";
import type { ModelConsumptionResponse, ModelTopN } from "../../types/metering";
import {
  buildModelBreakdownChart,
  buildTopModelsChart,
  deriveModelInsights,
  formatScaledCount,
  getWindowLabel,
} from "../../utils/meteringFormatters";
import { meteringServiceColor } from "../../utils/meteringColors";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringDonutChart, { DonutRankedLayout } from "./MeteringDonutChart";
import InfoTip from "../common/InfoTip";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import RankedShareList from "./RankedShareList";
import SegmentedTabBar from "./SegmentedTabBar";

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
  const [topN, setTopN] = useState<ModelTopN>(METERING.MODEL_TOP_N_DEFAULT);
  const breakdown = data?.breakdown ?? [];
  const topModels = data?.top_models ?? [];

  const visibleTopModels = useMemo(() => topModels.slice(0, topN), [topModels, topN]);

  const { slices } = useMemo(() => {
    if (visibleTopModels.length) return buildTopModelsChart(visibleTopModels);
    return buildModelBreakdownChart(breakdown);
  }, [visibleTopModels, breakdown]);

  const insights = useMemo(
    () => deriveModelInsights(data?.summary, breakdown),
    [data?.summary, breakdown],
  );

  const mostUsedHelper = insights
    ? `${formatScaledCount(insights.mostUsedRequests)} ${
        isPlatformWide
          ? section.REQUESTS_ACROSS_INSTITUTIONS
          : section.REQUESTS_ACROSS_INSTITUTION
      }`
    : undefined;

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
            <SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} spacing={4}>
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
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="green.400" />
                    <Text as="span">{insights.mostUsedName}</Text>
                  </HStack>
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
                />
              }
              list={
                <RankedShareList
                  rows={visibleTopModels.map((row) => ({
                    rank: row.rank,
                    label: row.model_name,
                    formattedValue: row.formatted_requests || formatScaledCount(row.requests),
                    percentage: row.consumption_pct,
                  }))}
                  headerLeft="Model"
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
            <MeteringDataTable>
              <Thead bg="gray.50">
                <Tr>
                  <InfoTip header={section.TABLE_MODEL} />
                  <InfoTip header={section.TABLE_SERVICE} />
                  <InfoTip
                    header={section.TABLE_TOTAL_REQUESTS}
                    message={section.TOOLTIPS.TOTAL_REQUESTS}
                    isNumeric
                  />
                  <InfoTip
                    header={section.TABLE_NATIVE}
                    message={section.TOOLTIPS.TOKEN_CONSUMPTION}
                    isNumeric
                  />
                  <InfoTip
                    header={section.TABLE_SUCCESS}
                    message={section.TOOLTIPS.SUCCESS_RATE}
                    isNumeric
                  />
                  <InfoTip
                    header={section.TABLE_FAILURE}
                    message={section.TOOLTIPS.FAILURE_RATE}
                    isNumeric
                  />
                </Tr>
              </Thead>
              <Tbody>
                {breakdown.map((row, i) => (
                  <Tr key={`${row.service_id}-${row.model_name ?? i}`}>
                    <Td fontSize="sm" color="gray.800" fontWeight="medium">
                      {row.model_name?.trim() || METERING.GRAPH.EMPTY_VALUE}
                    </Td>
                    <Td>
                      <HStack spacing={2}>
                        <Box w={1} h={5} borderRadius="sm" bg={meteringServiceColor(row.name, i)} />
                        <Text fontWeight="medium" fontSize="sm">
                          {row.name}
                        </Text>
                      </HStack>
                    </Td>
                    <Td isNumeric fontSize="sm">
                      {formatScaledCount(row.requests)}
                    </Td>
                    <Td isNumeric fontSize="sm" color="gray.600">
                      {formatScaledCount(row.native_units)}
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
