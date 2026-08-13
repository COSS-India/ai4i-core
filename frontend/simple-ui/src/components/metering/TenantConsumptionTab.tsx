import { Badge, HStack, Progress, Tbody, Td, Th, Thead, Tr, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { INSTITUTION } from "../../config/constants";
import type { MeteringTopN, TenantConsumptionResponse } from "../../types/metering";
import { meteringColorAt } from "../../utils/meteringColors";
import { formatTenantLabel, getWindowLabel } from "../../utils/meteringFormatters";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import MeteringTableText from "./MeteringTableText";
import SegmentedTabBar from "./SegmentedTabBar";
import TenantServiceHeatmapSection from "./TenantServiceHeatmapSection";

interface TenantConsumptionTabProps {
  data?: TenantConsumptionResponse;
  topN: MeteringTopN;
  onTopNChange: (n: MeteringTopN) => void;
  // UNDO: restore when re-enabling heatmap "Select services".
  // onHeatmapServicesChange?: (services: string[] | null) => void;
  tenantOrganisationById?: Record<string, string>;
  isLoading?: boolean;
  errorMessage?: string | null;
}

const TenantConsumptionTab: React.FC<TenantConsumptionTabProps> = ({
  data,
  topN,
  onTopNChange,
  // onHeatmapServicesChange,
  tenantOrganisationById = {},
  isLoading,
  errorMessage,
}) => {
  const section = METERING.SECTIONS.TENANT_RANKING;
  const windowLabel = data ? getWindowLabel(data.scope.window) : "";

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
            label={data.avg_requests_per_tenant?.label ?? `Average requests per ${INSTITUTION.toLowerCase()}`}
            value={data.avg_requests_per_tenant?.value ?? "—"}
            pctChange={data.avg_requests_per_tenant?.pct_change}
            helper={data.avg_requests_per_tenant?.helper ?? undefined}
            valueColor="gray.800"
          />
          <MeteringSectionCard
            title={section.TITLE}
            subtitle={`${section.SUBTITLE_PREFIX} ${windowLabel}`}
            sectionLabel
            action={
              <SegmentedTabBar
                options={[...METERING.TOP_N_SEGMENT_OPTIONS]}
                activeId={String(topN)}
                onChange={(id) => onTopNChange(Number(id) as MeteringTopN)}
              />
            }
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

          <TenantServiceHeatmapSection
            rows={data.usage_by_service}
            topN={topN}
            // UNDO: onServicesFilterChange={onHeatmapServicesChange}
            windowLabel={windowLabel}
            tenantOrganisationById={tenantOrganisationById}
          />
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default TenantConsumptionTab;
