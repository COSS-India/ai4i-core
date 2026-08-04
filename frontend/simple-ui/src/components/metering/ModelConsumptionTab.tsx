import {
  Box,
  HStack,
  SimpleGrid,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { ModelConsumptionResponse } from "../../types/metering";
import {
  buildModelBreakdownChart,
  deriveModelInsights,
  formatCompactNumber,
  formatNativeConsumption,
  getWindowLabel,
} from "../../utils/meteringFormatters";
import { meteringServiceColor } from "../../utils/meteringColors";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringDonutChart from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";

interface ModelConsumptionTabProps {
  data?: ModelConsumptionResponse;
  isLoading?: boolean;
  errorMessage?: string | null;
}

const ModelConsumptionTab: React.FC<ModelConsumptionTabProps> = ({
  data,
  isLoading,
  errorMessage,
}) => {
  const section = METERING.SECTIONS.MODEL;
  const breakdown = data?.breakdown ?? [];

  const { slices } = useMemo(() => buildModelBreakdownChart(breakdown), [breakdown]);
  const insights = useMemo(
    () => deriveModelInsights(data?.summary, breakdown),
    [data?.summary, breakdown],
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
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <KpiCard
                label={section.MOST_USED}
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="green.400" />
                    <Text as="span">{insights.mostUsedName}</Text>
                  </HStack>
                }
                helper={`${formatCompactNumber(insights.mostUsedRequests, "indian")} ${section.REQUESTS_SUFFIX}`}
                valueColor="gray.800"
              />
              <KpiCard
                label={section.HIGHEST_FAILURE}
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="pink.300" />
                    <Text as="span" color="orange.600">
                      {insights.highestFailureName}
                    </Text>
                  </HStack>
                }
                helper={`${insights.highestFailureRate.toFixed(2)}% ${METERING.SECTIONS.REQUEST_VOLUME.FAILURE_RATE_SUFFIX}`}
                valueColor="gray.800"
              />
            </SimpleGrid>
          ) : null}

          <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel>
            <MeteringDonutChart
              data={slices.map(({ name, value, color }) => ({ name, value, color }))}
              legendItems={slices.map(({ name, color, pct }) => ({ name, color, pct }))}
              height={300}
              innerRadius={70}
              outerRadius={110}
              centerPrimary={section.DONUT_PRIMARY}
              centerSecondary={section.DONUT_SECONDARY}
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
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500">
                    {section.TABLE_SERVICE}
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500">
                    {section.TABLE_MODEL}
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    {section.TABLE_TOTAL_REQUESTS}
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    {section.TABLE_NATIVE}
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    {section.TABLE_SUCCESS}
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    {section.TABLE_FAILURE}
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {breakdown.map((row, i) => (
                  <Tr key={`${row.service_id}-${row.model_name ?? i}`}>
                    <Td>
                      <HStack spacing={2}>
                        <Box w={1} h={5} borderRadius="sm" bg={meteringServiceColor(row.name, i)} />
                        <Text fontWeight="medium" fontSize="sm">{row.name}</Text>
                      </HStack>
                    </Td>
                    <Td fontSize="sm" color="gray.600">
                      {row.model_name?.trim() || METERING.GRAPH.EMPTY_VALUE}
                    </Td>
                    <Td isNumeric fontSize="sm">{formatCompactNumber(row.requests, "indian")}</Td>
                    <Td isNumeric fontSize="sm" color="gray.600">
                      {formatNativeConsumption(row.native_units, row.native_unit_suffix)}
                    </Td>
                    <Td isNumeric fontSize="sm" color="green.600" fontWeight="medium">
                      {row.success_pct.toFixed(2)}%
                    </Td>
                    <Td isNumeric fontSize="sm" color="red.500" fontWeight="medium">
                      {row.failure_rate_pct.toFixed(2)}%
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
