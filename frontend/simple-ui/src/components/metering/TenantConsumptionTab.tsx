import { Badge, HStack, Progress, Tbody, Td, Th, Thead, Tr, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { MeteringTopN, TenantConsumptionResponse } from "../../types/metering";
import { meteringColorAt } from "../../utils/meteringColors";
import { formatCompactNumber, formatTenantLabel, getWindowLabel } from "../../utils/meteringFormatters";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import MeteringTableText from "./MeteringTableText";
import TenantServiceHeatmapSection from "./TenantServiceHeatmapSection";
import ThroughputLoadSection from "./ThroughputLoadSection";

interface TenantConsumptionTabProps {
  data?: TenantConsumptionResponse;
  topN: MeteringTopN;
  onTopNChange: (n: MeteringTopN) => void;
  onHeatmapServicesChange?: (services: string[] | null) => void;
  tenantOrganisationById?: Record<string, string>;
  isLoading?: boolean;
  errorMessage?: string | null;
}

const TenantConsumptionTab: React.FC<TenantConsumptionTabProps> = ({
  data,
  topN,
  onTopNChange,
  onHeatmapServicesChange,
  tenantOrganisationById = {},
  isLoading,
  errorMessage,
}) => {
  const section = METERING.SECTIONS.TENANT_RANKING;
  const windowLabel = data ? getWindowLabel(data.scope.window) : "";
  const totalRankedRequests = data?.tenant_ranking.reduce((sum, row) => sum + row.requests, 0) ?? 0;

  return (
    <MeteringAsyncState
      isLoading={isLoading}
      isEmpty={!data}
      errorMessage={errorMessage}
      emptyMessage={METERING.EMPTY.TENANT_CONSUMPTION}
    >
      {data ? (
        <VStack align="stretch" spacing={6}>
          <KpiCard
            label={data.avg_requests_per_tenant?.label ?? "Average requests per tenant"}
            value={data.avg_requests_per_tenant?.value ?? "—"}
            pctChange={data.avg_requests_per_tenant?.pct_change}
            helper={data.avg_requests_per_tenant?.helper ?? undefined}
            accent="gray"
          />
          <MeteringSectionCard
            title={section.TITLE}
            subtitle={`${section.SUBTITLE_PREFIX} ${windowLabel}`}
            sectionLabel
          >
            <MeteringDataTable>
              <Thead bg="gray.50">
                <Tr>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" w="72px">
                    Rank
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" minW="240px">
                    Tenant
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    Requests
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" minW="180px">
                    Share
                  </Th>
                  <Th fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric>
                    %
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {data.tenant_ranking.map((row, i) => (
                  <Tr key={row.rank}>
                    <Td>
                      <Badge
                        colorScheme="gray"
                        variant="solid"
                        bg={meteringColorAt(i)}
                        color="white"
                        borderRadius="md"
                        fontSize="xs"
                        display="inline-flex"
                      >
                        #{row.rank}
                      </Badge>
                    </Td>
                    <Td>
                      <HStack spacing={2} minW={0}>
                        <MeteringTableText>
                          {formatTenantLabel(row.tenant, row.organisation, tenantOrganisationById)}
                        </MeteringTableText>
                        {row.plan ? (
                          <Badge
                            colorScheme="gray"
                            variant="subtle"
                            fontSize="xs"
                            flexShrink={0}
                          >
                            {row.plan}
                          </Badge>
                        ) : null}
                      </HStack>
                    </Td>
                    <Td isNumeric fontSize="sm" fontWeight="semibold">
                      {row.formatted_requests}
                    </Td>
                    <Td>
                      <Progress
                        value={row.percentage}
                        size="sm"
                        borderRadius="full"
                        bg="gray.100"
                        sx={{ "& > div": { background: meteringColorAt(i) } }}
                      />
                    </Td>
                    <Td isNumeric fontSize="sm" color="gray.600">
                      {row.percentage.toFixed(2)}%
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </MeteringDataTable>
          </MeteringSectionCard>

          <ThroughputLoadSection
            throughput={data.throughput}
            timeWindow={data.scope.window}
            requestVolumeGraph={data.request_volume}
            fourthMetric={{
              label: section.RANKED_REQUESTS_LABEL,
              value: formatCompactNumber(totalRankedRequests, "indian"),
              helper: section.RANKED_REQUESTS_HELPER,
            }}
          />

          <TenantServiceHeatmapSection
            rows={data.usage_by_service}
            topN={topN}
            onTopNChange={onTopNChange}
            onServicesFilterChange={onHeatmapServicesChange}
            windowLabel={windowLabel}
            tenantOrganisationById={tenantOrganisationById}
          />
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default TenantConsumptionTab;
