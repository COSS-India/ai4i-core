import {
  Box,
  Button,
  Checkbox,
  Flex,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Progress,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import { ChevronDownIcon } from "@chakra-ui/icons";
import React, { useEffect, useMemo, useState } from "react";
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
import SegmentedTabBar from "./SegmentedTabBar";

interface TenantServiceHeatmapSectionProps {
  rows: TenantServiceRow[];
  topN: MeteringTopN;
  onTopNChange: (n: MeteringTopN) => void;
  onServicesFilterChange?: (services: string[] | null) => void;
  windowLabel: string;
  tenantOrganisationById?: Record<string, string>;
}

const TenantServiceHeatmapSection: React.FC<TenantServiceHeatmapSectionProps> = ({
  rows,
  topN,
  onTopNChange,
  onServicesFilterChange,
  windowLabel,
  tenantOrganisationById = {},
}) => {
  const availableServiceKeys = useMemo(() => {
    const fromData = new Set<string>();
    rows.forEach((row) => {
      Object.keys(row.services).forEach((k) => fromData.add(k));
    });
    return METERING.HEATMAP.SERVICES.filter(
      (s) => fromData.size === 0 || fromData.has(s.key),
    );
  }, [rows]);

  const heatmap = METERING.HEATMAP;
  const heatmapLegendColors = useMemo(() => getHeatmapLegendColors(), []);

  const [selectedServices, setSelectedServices] = useState<Set<string>>(() =>
    new Set(availableServiceKeys.map((s) => s.key)),
  );

  useEffect(() => {
    if (availableServiceKeys.length === 0) return;
    setSelectedServices((prev) => {
      if (prev.size > 0) return prev;
      return new Set(availableServiceKeys.map((s) => s.key));
    });
  }, [availableServiceKeys]);

  const notifyServicesFilter = (next: Set<string>) => {
    if (!onServicesFilterChange) return;
    const allKeys = availableServiceKeys.map((s) => s.key);
    const isAllSelected =
      allKeys.length > 0 && allKeys.every((key) => next.has(key));
    onServicesFilterChange(isAllSelected ? null : Array.from(next).sort((a, b) => a.localeCompare(b)));
  };

  const visibleServices = useMemo(
    () => availableServiceKeys.filter((s) => selectedServices.has(s.key)),
    [availableServiceKeys, selectedServices],
  );

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

  const topNControls = (
    <SegmentedTabBar
      options={[...METERING.TOP_N_SEGMENT_OPTIONS]}
      activeId={String(topN)}
      onChange={(id) => onTopNChange(Number(id) as MeteringTopN)}
    />
  );

  const serviceFilter = (
    <Menu closeOnSelect={false}>
      <MenuButton
        as={Button}
        size="sm"
        variant="outline"
        rightIcon={<ChevronDownIcon />}
        bg="white"
        fontWeight="normal"
      >
        Select services ({selectedServices.size})
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
  );

  if (!rows.length) {
    return (
      <MeteringSectionCard
        title={heatmap.TITLE}
        subtitle={`${heatmap.SUBTITLE_PREFIX} ${windowLabel}`}
        sectionLabel
        action={
          <HStack spacing={3} flexWrap="wrap">
            {topNControls}
            {serviceFilter}
          </HStack>
        }
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
      action={
        <HStack spacing={3} flexWrap="wrap" justify="flex-end">
          {topNControls}
          {serviceFilter}
        </HStack>
      }
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
