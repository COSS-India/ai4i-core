import { Badge, HStack, Progress, Tbody, Td, Thead, Tr, VStack } from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { MeteringTopN, TenantConsumptionResponse } from "../../types/metering";
import { meteringColorAt } from "../../utils/meteringColors";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
import { formatTenantLabel, getWindowLabel } from "../../utils/meteringFormatters";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import { ThWithTip } from "../common/InfoTip";
import MeteringSectionCard, { KpiCard } from "./MeteringSectionCard";
import MeteringTableText from "./MeteringTableText";
import SegmentedTabBar from "./SegmentedTabBar";

interface TenantConsumptionTabProps {
  data?: TenantConsumptionResponse;
  topN: MeteringTopN;
  onTopNChange: (n: MeteringTopN) => void;
  tenantOrganisationById?: Record<string, string>;
  /** True when the All Institutions filter is narrowed to one institution. */
  isScopedTenant?: boolean;
  isLoading?: boolean;
  errorMessage?: string | null;
}

const TenantConsumptionTab: React.FC<TenantConsumptionTabProps> = ({
  data,
  topN,
  onTopNChange,
  tenantOrganisationById = {},
  isScopedTenant = false,
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
          {isScopedTenant ? null : (
            <KpiCard
              label={section.AVG_REQUESTS_LABEL}
              value={data.avg_requests_per_tenant?.value ?? "—"}
              pctChange={data.avg_requests_per_tenant?.pct_change}
              helper={data.avg_requests_per_tenant?.helper ?? undefined}
              tooltip={section.TOOLTIPS.AVG_REQUESTS}
              valueColor="gray.800"
            />
          )}
          <MeteringSectionCard
            title={section.TITLE}
            subtitle={`${section.SUBTITLE_PREFIX} ${windowLabel}`}
            sectionLabel
            action={
              isScopedTenant ? undefined : (
                <SegmentedTabBar
                  options={[...METERING.TOP_N_SEGMENT_OPTIONS]}
                  activeId={String(topN)}
                  onChange={(id) => onTopNChange(Number(id) as MeteringTopN)}
                />
              )
            }
          >
            <MeteringDataTable>
              <Thead bg="gray.50">
                <Tr>
                  <ThWithTip w="72px">{section.TABLE_RANK}</ThWithTip>
                  <ThWithTip minW="240px">
                    {replaceTenantCopy(section.TABLE_INSTITUTION)}
                  </ThWithTip>
                  <ThWithTip message={section.TOOLTIPS.REQUESTS} isNumeric>
                    {section.TABLE_REQUESTS}
                  </ThWithTip>
                  <ThWithTip message={section.TOOLTIPS.SHARE} minW="180px">
                    {section.TABLE_SHARE}
                  </ThWithTip>
                  <ThWithTip message={section.TOOLTIPS.SHARE} isNumeric>
                    %
                  </ThWithTip>
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
                      {row.percentage.toFixed(2)}
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

export default TenantConsumptionTab;
