import {
  Box,
  Flex,
  HStack,
  Progress,
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
import type { MeteringTopN, TenantServiceRow } from "../../types/metering";
import { formatTenantLabel } from "../../utils/meteringFormatters";
import {
  getHeatmapLegendColors,
  heatmapIntensityColor,
  heatmapTextColor,
  meteringColorAt,
  meteringServiceColor,
} from "../../utils/meteringColors";
import MeteringDataTable from "./MeteringDataTable";
import MeteringSectionCard from "./MeteringSectionCard";
import MeteringTableText from "./MeteringTableText";

type HeatmapServiceMeta = (typeof METERING.HEATMAP.SERVICES)[number];

interface TenantServiceHeatmapSectionProps {
  rows: TenantServiceRow[];
  /** Service columns to render — selection is owned by the Tenant Ranking header. */
  visibleServices: ReadonlyArray<HeatmapServiceMeta>;
  topN: MeteringTopN;
  windowLabel: string;
  tenantOrganisationById?: Record<string, string>;
}

const TenantServiceHeatmapSection: React.FC<TenantServiceHeatmapSectionProps> = ({
  rows,
  visibleServices,
  topN,
  windowLabel,
  tenantOrganisationById = {},
}) => {
  const heatmap = METERING.HEATMAP;
  const heatmapLegendColors = useMemo(() => getHeatmapLegendColors(), []);

  const maxCellValue = useMemo(() => {
    let max = 0;
    rows.forEach((row) => {
      visibleServices.forEach((svc) => {
        const v = row.services[svc.key]?.requests ?? 0;
        if (v > max) max = v;
      });
    });
    return max;
  }, [rows, visibleServices]);

  const maxTotal = useMemo(
    () => Math.max(...rows.map((r) => r.total), 0),
    [rows],
  );

  if (!rows.length) {
    return (
      <MeteringSectionCard
        title={heatmap.TITLE}
        subtitle={`${heatmap.SUBTITLE_PREFIX} ${windowLabel}`}
        sectionLabel
      >
        <Flex h="200px" align="center" justify="center">
          <Text color="gray.500" fontSize="sm">
            {heatmap.EMPTY}
          </Text>
        </Flex>
      </MeteringSectionCard>
    );
  }

  return (
    <MeteringSectionCard
      title={heatmap.TITLE}
      subtitle={`${heatmap.SUBTITLE_PREFIX} ${windowLabel}`}
      sectionLabel
    >
      <MeteringDataTable>
        <Thead>
          <Tr>
            <Th
              fontSize="xs"
              textTransform="uppercase"
              color="gray.500"
              bg="gray.50"
              minW="220px"
              position="sticky"
              left={0}
              zIndex={1}
            >
              {heatmap.TABLE_TENANT}
            </Th>
            {visibleServices.map((svc, i) => (
              <Th
                key={svc.key}
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                bg="gray.50"
                isNumeric
                px={2}
                minW="72px"
              >
                <VStack spacing={1} align="center">
                  <Box
                    w="full"
                    h="3px"
                    borderRadius="sm"
                    bg={meteringServiceColor(svc.displayName, i)}
                  />
                  <Text>{svc.shortLabel}</Text>
                </VStack>
              </Th>
            ))}
            <Th fontSize="xs" textTransform="uppercase" color="gray.500" bg="gray.50" isNumeric minW="100px">
              {heatmap.TABLE_TOTAL}
            </Th>
          </Tr>
        </Thead>
        <Tbody>
          {rows.map((row, rowIndex) => (
            <Tr key={`${row.rank}-${row.tenant}`}>
              <Td
                bg="white"
                position="sticky"
                left={0}
                zIndex={1}
                borderRightWidth="1px"
                borderColor="gray.100"
              >
                <HStack spacing={2} minW={0}>
                  <Box
                    w={2}
                    h={2}
                    borderRadius="full"
                    bg={meteringColorAt(rowIndex)}
                    flexShrink={0}
                  />
                  <MeteringTableText maxW="200px">
                    {formatTenantLabel(row.tenant, row.organisation, tenantOrganisationById)}
                  </MeteringTableText>
                </HStack>
              </Td>
              {visibleServices.map((svc) => {
                const entry = row.services[svc.key];
                const requests = entry?.requests ?? 0;
                const intensity = maxCellValue > 0 ? requests / maxCellValue : 0;
                return (
                  <Td
                    key={svc.key}
                    isNumeric
                    fontSize="sm"
                    fontWeight="medium"
                    px={2}
                    bg={heatmapIntensityColor(intensity)}
                    color={heatmapTextColor(intensity)}
                  >
                    {entry?.formatted_requests ?? (requests > 0 ? requests.toLocaleString() : "0")}
                  </Td>
                );
              })}
              <Td isNumeric bg="white" px={3}>
                <VStack align="stretch" spacing={1}>
                  <Text fontSize="sm" fontWeight="bold" color="gray.800" textAlign="right">
                    {row.formatted_total}
                  </Text>
                  <Progress
                    value={maxTotal > 0 ? (row.total / maxTotal) * 100 : 0}
                    size="xs"
                    borderRadius="full"
                    colorScheme="orange"
                    bg="gray.100"
                  />
                </VStack>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </MeteringDataTable>

      <Flex
        mt={4}
        pt={3}
        borderTopWidth="1px"
        borderColor="gray.100"
        justify="space-between"
        align="center"
        flexWrap="wrap"
        gap={3}
      >
        <VStack align="flex-start" spacing={0}>
          <Text fontSize="xs" color="gray.500">
            {heatmap.FOOTER_PRIMARY.replace("{topN}", String(topN))}
          </Text>
          <Text fontSize="xs" color="gray.400">
            {heatmap.FOOTER_SECONDARY}
          </Text>
        </VStack>
        <HStack spacing={2}>
          <Text fontSize="xs" color="gray.500">
            {heatmap.LEGEND_LOW}
          </Text>
          {heatmapLegendColors.map((color) => (
            <Box key={color} w={4} h={4} borderRadius="sm" bg={color} borderWidth="1px" borderColor="gray.200" />
          ))}
          <Text fontSize="xs" color="gray.500">
            {heatmap.LEGEND_HIGH}
          </Text>
        </HStack>
      </Flex>
    </MeteringSectionCard>
  );
};

export default TenantServiceHeatmapSection;
