import { Box, HStack, SimpleGrid, Tbody, Td, Text, Th, Thead, Tr, VStack } from "@chakra-ui/react";
import React, { useMemo } from "react";
import type { ServiceConsumptionResponse, ServiceRow } from "../../types/metering";
import {
  getWindowLabel,
  formatNativeConsumption,
  formatCompactNumber,
  meteringServiceColor,
} from "../../utils/meteringFormatters";
import DonutWithLegend from "./DonutWithLegend";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import { KpiCard } from "./MeteringSectionCard";
import MeteringSectionCard from "./MeteringSectionCard";
import ThroughputLoadSection from "./ThroughputLoadSection";

const formatNative = (row: ServiceRow): string =>
  formatNativeConsumption(row.native_units, row.native_unit_suffix);

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
  const breakdown = data?.service_breakdown ?? [];
  const totalRequests = breakdown.reduce((sum, s) => sum + s.requests, 0);

  const pieData = useMemo(
    () =>
      breakdown.map((s, i) => ({
        name: s.service,
        value: s.requests,
        color: meteringServiceColor(s.service, i),
      })),
    [breakdown],
  );

  const legendItems = useMemo(
    () =>
      pieData.map((row, i) => {
        const svc = breakdown[i];
        const pct =
          svc?.percentage ??
          (totalRequests > 0 ? (row.value / totalRequests) * 100 : 0);
        return {
          name: row.name,
          color: row.color,
          pct,
        };
      }),
    [pieData, breakdown, totalRequests],
  );

  const insights = useMemo(() => {
    if (data?.summary) {
      const { summary } = data;
      return {
        activeCount: summary.active_services,
        mostUsed: summary.most_used,
        highestFailureRate: summary.highest_failure_rate.failure_rate_pct,
        highestFailureService: summary.highest_failure_rate.service,
      };
    }
    if (!breakdown.length) return null;
    const active = breakdown.filter((s) => s.requests > 0);
    const mostUsed = [...breakdown].sort((a, b) => b.requests - a.requests)[0];
    const highestFailure = [...breakdown].sort(
      (a, b) =>
        (a.failure_rate_pct ?? 100 - a.success_pct) -
        (b.failure_rate_pct ?? 100 - b.success_pct),
    )[0];
    return {
      activeCount: active.length,
      mostUsed: { service: mostUsed.service, requests: mostUsed.requests },
      highestFailureRate: highestFailure.failure_rate_pct ?? 100 - highestFailure.success_pct,
      highestFailureService: highestFailure.service,
    };
  }, [data?.summary, breakdown]);

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!data}
      errorMessage={errorMessage}
      emptyMessage="No service consumption data available."
    >
      {data ? (
        <VStack align="stretch" spacing={6}>
          {insights ? (
            <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
              <KpiCard
                label="Active services"
                value={insights.activeCount}
                helper="with requests in selected window"
                accent="gray"
              />
              <KpiCard
                label="Most used service"
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="green.400" />
                    <Text as="span">{insights.mostUsed.service}</Text>
                  </HStack>
                }
                helper={`${formatCompactNumber(insights.mostUsed.requests, "indian")} requests`}
                accent="gray"
              />
              <KpiCard
                label="Highest failure rate"
                value={
                  <HStack spacing={2}>
                    <Box w={2} h={2} borderRadius="full" bg="pink.300" />
                    <Text as="span" color="orange.600">
                      {insights.highestFailureService}
                    </Text>
                  </HStack>
                }
                helper={`${insights.highestFailureRate.toFixed(2)}% failure rate`}
                accent="gray"
              />
            </SimpleGrid>
          ) : null}

          <ThroughputLoadSection
            throughput={data.throughput}
            window={data.scope.window}
            requestVolumeGraph={data.request_volume}
          />

          <MeteringSectionCard
            title="Service consumption"
            subtitle="Platform-wide request distribution · reflects selected time window"
            sectionLabel
          >
            <DonutWithLegend
              data={pieData}
              legendItems={legendItems}
              height={300}
              innerRadius={70}
              outerRadius={110}
              centerPrimary="All"
              centerSecondary="Services"
            />
          </MeteringSectionCard>

          <MeteringSectionCard
            title="Service breakdown"
            subtitle={`Consumption across all services · ${getWindowLabel(data.scope.window)}`}
            sectionLabel
            bare
          >
            <MeteringDataTable>
              <Thead bg="gray.50">
                <Tr>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500">
                    Service
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    Total requests
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    Native consumption
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    Success rate %
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    Failure rate %
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {breakdown.map((row, i) => {
                  const failureRate = row.failure_rate_pct ?? 100 - row.success_pct;
                  return (
                    <Tr key={row.service}>
                      <Td>
                        <HStack spacing={2}>
                          <Box w={1} h={5} borderRadius="sm" bg={meteringServiceColor(row.service, i)} />
                          <Text fontWeight="medium" fontSize="sm">
                            {row.service}
                          </Text>
                        </HStack>
                      </Td>
                      <Td isNumeric fontSize="sm">
                        {formatCompactNumber(row.requests, "indian")}
                      </Td>
                      <Td isNumeric fontSize="sm" color="gray.600">
                        {formatNative(row)}
                      </Td>
                      <Td isNumeric fontSize="sm" color="green.600" fontWeight="medium">
                        {row.success_pct.toFixed(2)}%
                      </Td>
                      <Td isNumeric fontSize="sm" color="red.500" fontWeight="medium">
                        {failureRate.toFixed(2)}%
                      </Td>
                    </Tr>
                  );
                })}
              </Tbody>
            </MeteringDataTable>
          </MeteringSectionCard>
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default ServiceConsumptionTab;
