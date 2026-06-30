import {
  Badge,
  Button,
  Checkbox,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Progress,
  Tbody,
  Td,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import React, { useEffect, useMemo, useState } from "react";
import { METERING } from "../../config/meteringConstants";
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

  const heatmapRows = data?.usage_by_service ?? [];

  // Service-column selection is owned here (not in the heatmap) so the Top N +
  // service controls render in the Tenant Ranking header per the design; the
  // heatmap below just renders the chosen columns.
  const availableServiceKeys = useMemo(() => {
    const fromData = new Set<string>();
    heatmapRows.forEach((row) => {
      Object.keys(row.services).forEach((k) => fromData.add(k));
    });
    return METERING.HEATMAP.SERVICES.filter(
      (s) => fromData.size === 0 || fromData.has(s.key),
    );
  }, [heatmapRows]);

  const [selectedServices, setSelectedServices] = useState<Set<string>>(
    () => new Set(METERING.HEATMAP.SERVICES.map((s) => s.key)),
  );

  useEffect(() => {
    if (availableServiceKeys.length === 0) return;
    setSelectedServices((prev) => {
      if (prev.size > 0) return prev;
      return new Set(availableServiceKeys.map((s) => s.key));
    });
  }, [availableServiceKeys]);

  const notifyServicesFilter = (next: Set<string>) => {
    if (!onHeatmapServicesChange) return;
    const allKeys = availableServiceKeys.map((s) => s.key);
    const isAllSelected =
      allKeys.length > 0 && allKeys.every((key) => next.has(key));
    onHeatmapServicesChange(
      isAllSelected ? null : Array.from(next).sort((a, b) => a.localeCompare(b)),
    );
  };

  const toggleService = (key: string) => {
    setSelectedServices((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key);
      } else {
        next.add(key);
      }
      notifyServicesFilter(next);
      return next;
    });
  };

  const visibleServices = useMemo(
    () => availableServiceKeys.filter((s) => selectedServices.has(s.key)),
    [availableServiceKeys, selectedServices],
  );

  const rankingControls = (
    <HStack spacing={3} flexWrap="wrap" justify="flex-end">
      <SegmentedTabBar
        options={[...METERING.TOP_N_SEGMENT_OPTIONS]}
        activeId={String(topN)}
        onChange={(id) => onTopNChange(Number(id) as MeteringTopN)}
      />
      <Menu closeOnSelect={false}>
        <MenuButton
          as={Button}
          size="sm"
          variant="outline"
          rightIcon={<ChevronDownIcon />}
          bg="white"
          fontWeight="normal"
        >
          Select services ({visibleServices.length})
        </MenuButton>
        <MenuList maxH="320px" overflowY="auto" minW="220px">
          {availableServiceKeys.map((svc) => (
            <MenuItem key={svc.key} onClick={() => toggleService(svc.key)}>
              <Checkbox
                isChecked={selectedServices.has(svc.key)}
                pointerEvents="none"
                mr={2}
                colorScheme="orange"
              />
              {svc.displayName}
            </MenuItem>
          ))}
        </MenuList>
      </Menu>
    </HStack>
  );

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
            helper={data.avg_requests_per_tenant?.helper}
            accent="gray"
          />
          <MeteringSectionCard
            title={section.TITLE}
            subtitle={`${section.SUBTITLE_PREFIX} ${windowLabel}`}
            sectionLabel
            action={rankingControls}
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
            visibleServices={visibleServices}
            topN={topN}
            windowLabel={windowLabel}
            tenantOrganisationById={tenantOrganisationById}
          />
        </VStack>
      ) : null}
    </MeteringAsyncState>
  );
};

export default TenantConsumptionTab;
