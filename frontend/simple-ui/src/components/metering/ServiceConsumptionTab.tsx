import { Box, HStack, Tbody, Td, Text, Th, Thead, Tr, VStack } from "@chakra-ui/react";
// AI4IDS-2588: UNDO — restore SimpleGrid + KpiCard when re-enabling insight KPIs
// import { Box, HStack, SimpleGrid, Tbody, Td, Text, Th, Thead, Tr, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { ServiceConsumptionResponse } from "../../types/metering";
import {
  buildServiceBreakdownChart,
  // AI4IDS-2588: UNDO — restore deriveServiceInsights
  // deriveServiceInsights,
  formatCompactNumber,
  formatNativeConsumption,
  getWindowLabel,
  serviceFailureRate,
} from "../../utils/meteringFormatters";
import { meteringServiceColor } from "../../utils/meteringColors";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringDonutChart from "./MeteringDonutChart";
// AI4IDS-2588: UNDO — import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import MeteringSectionCard from "./MeteringSectionCard";

interface ServiceConsumptionTabProps {
  data?: ServiceConsumptionResponse;
  isLoading?: boolean;
  errorMessage?: string | null;
}

const ServiceConsumptionTab: React.FC<ServiceConsumptionTabProps> = ({
  data,
  isLoading,
  errorMessage,
}) => {
  const section = METERING.SECTIONS.SERVICE;
  // Backend query-filters service_breakdown by the frontend-passed services=,
  // so the rows come back already scoped — no client-side filter here.
  const breakdown = data?.service_breakdown ?? [];

  const { slices } = useMemo(() => buildServiceBreakdownChart(breakdown), [breakdown]);
  // AI4IDS-2588: UNDO — restore Most used / Highest failure KPI cards
  // const insights = useMemo(
  //   () => deriveServiceInsights(data?.summary, breakdown),
  //   [data?.summary, breakdown],
  // );

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!data}
      errorMessage={errorMessage}
      emptyMessage={METERING.EMPTY.SERVICE_CONSUMPTION}
    >
      {data ? (
        <VStack align="stretch" spacing={6}>
          {/* AI4IDS-2588: UNDO — restore insight KPI cards
          {insights ? (
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <KpiCard
                label={section.MOST_USED}
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="green.400" />
                    <Text as="span">{insights.mostUsed.service}</Text>
                  </HStack>
                }
                helper={`${formatCompactNumber(insights.mostUsed.requests, "indian")} ${section.REQUESTS_SUFFIX}`}
                valueColor="gray.800"
              />
              <KpiCard
                label={section.HIGHEST_FAILURE}
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="pink.300" />
                    <Text as="span" color="orange.600">
                      {insights.highestFailureService}
                    </Text>
                  </HStack>
                }
                helper={`${insights.highestFailureRate.toFixed(2)}% ${METERING.SECTIONS.REQUEST_VOLUME.FAILURE_RATE_SUFFIX}`}
                valueColor="gray.800"
              />
            </SimpleGrid>
          ) : null}
          */}

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
                  {/* AI4IDS-2588: UNDO — "Service" */}
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500">
                    {section.TABLE_SERVICE}
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
                  <Tr key={row.service}>
                    <Td>
                      <HStack spacing={2}>
                        <Box w={1} h={5} borderRadius="sm" bg={meteringServiceColor(row.service, i)} />
                        <Text fontWeight="medium" fontSize="sm">{row.service}</Text>
                      </HStack>
                    </Td>
                    <Td isNumeric fontSize="sm">{formatCompactNumber(row.requests, "indian")}</Td>
                    <Td isNumeric fontSize="sm" color="gray.600">
                      {formatNativeConsumption(row.native_units, row.native_unit_suffix)}
                    </Td>
                    <Td isNumeric fontSize="sm" color="green.600" fontWeight="medium">
                      {row.success_pct.toFixed(2)}%
                    </Td>
                    <Td isNumeric fontSize="sm" color="red.500" fontWeight="medium">
                      {serviceFailureRate(row).toFixed(2)}%
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

export default ServiceConsumptionTab;
