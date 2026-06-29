import { Box, HStack, SimpleGrid, Tbody, Td, Text, Th, Thead, Tr, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import { METERING } from "../../config/meteringConstants";
import type { ServiceConsumptionResponse } from "../../types/metering";
import {
  buildServiceBreakdownChart,
  deriveServiceInsights,
  formatCompactNumber,
  formatNativeConsumption,
  getWindowLabel,
  serviceFailureRate,
} from "../../utils/meteringFormatters";
import { meteringServiceColor } from "../../utils/meteringColors";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringDonutChart from "./MeteringDonutChart";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import ThroughputLoadSection from "./ThroughputLoadSection";

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
  const breakdown = data?.service_breakdown ?? [];

  const { slices } = useMemo(
    () => buildServiceBreakdownChart(breakdown),
    [breakdown],
  );

  const insights = useMemo(
    () => deriveServiceInsights(data?.summary, breakdown),
    [data?.summary, breakdown],
  );

  const pieData = useMemo(
    () => slices.map(({ name, value, color }) => ({ name, value, color })),
    [slices],
  );

  const legendItems = useMemo(
    () => slices.map(({ name, color, pct }) => ({ name, color, pct })),
    [slices],
  );

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!data}
      errorMessage={errorMessage}
      emptyMessage={METERING.EMPTY.SERVICE_CONSUMPTION}
    >
      {data ? (
        <VStack align="stretch" spacing={6}>
          {insights ? (
            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
              <KpiCard
                label={section.ACTIVE_SERVICES}
                value={insights.activeCount}
                helper={section.ACTIVE_SERVICES_HELPER}
                accent="gray"
              />
              <KpiCard
                label={section.MOST_USED}
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="green.400" />
                    <Text as="span">{insights.mostUsed.service}</Text>
                  </HStack>
                }
                helper={`${formatCompactNumber(insights.mostUsed.requests, "indian")} ${section.REQUESTS_SUFFIX}`}
                accent="gray"
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
                accent="gray"
              />
            </SimpleGrid>
          ) : null}

          <ThroughputLoadSection
            throughput={data.throughput}
            timeWindow={data.scope.window}
            requestVolumeGraph={data.request_volume}
          />

          <MeteringSectionCard title={section.TITLE} subtitle={section.SUBTITLE} sectionLabel>
            <MeteringDonutChart
              data={pieData}
              legendItems={legendItems}
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
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500">Service</Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>Total requests</Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>Native consumption</Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>Success rate %</Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>Failure rate %</Th>
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
