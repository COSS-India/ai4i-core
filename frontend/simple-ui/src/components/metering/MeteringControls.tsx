import {
  Box,
  Button,
  ButtonGroup,
  HStack,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import { RepeatIcon } from "@chakra-ui/icons";
import React from "react";
import { METERING, type MeteringSubTab } from "../../config/meteringConstants";
import type { MeteringTopN, MeteringWindow } from "../../types/metering";
import SegmentedTabBar from "./SegmentedTabBar";

interface MeteringControlsProps {
  timeWindow: MeteringWindow;
  onTimeWindowChange: (w: MeteringWindow) => void;
  topN?: MeteringTopN;
  onTopNChange?: (n: MeteringTopN) => void;
  showTopN?: boolean;
  showTenantFilter?: boolean;
  tenantOptions?: { id: string; label: string }[];
  selectedTenantId?: string;
  onTenantChange?: (id: string) => void;
  lastRefreshed?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  subTab?: MeteringSubTab;
  onSubTabChange?: (tab: MeteringSubTab) => void;
  showSubTabs?: boolean;
}

const MeteringControls: React.FC<MeteringControlsProps> = ({
  timeWindow,
  onTimeWindowChange,
  topN,
  onTopNChange,
  showTopN = false,
  showTenantFilter = false,
  tenantOptions = [],
  selectedTenantId = "",
  onTenantChange,
  lastRefreshed,
  onRefresh,
  isRefreshing,
  subTab,
  onSubTabChange,
  showSubTabs = false,
}) => (
  <VStack align="stretch" spacing={3}>
    <ButtonGroup size="sm" isAttached variant="outline" flexWrap="wrap">
      {METERING.TIME_WINDOWS.map((opt) => (
        <Button
          key={opt.value}
          onClick={() => onTimeWindowChange(opt.value)}
          colorScheme={timeWindow === opt.value ? "orange" : "gray"}
          variant={timeWindow === opt.value ? "solid" : "outline"}
          fontWeight={timeWindow === opt.value ? "semibold" : "normal"}
          borderRadius="full"
        >
          {opt.label}
        </Button>
      ))}
    </ButtonGroup>

    <HStack spacing={3} flexWrap="wrap" justify="space-between" align="flex-end">
      <HStack spacing={3} flexWrap="wrap" align="flex-end">
        {showTenantFilter ? (
          <Select
            size="sm"
            w="200px"
            value={selectedTenantId}
            onChange={(e) => onTenantChange?.(e.target.value)}
            bg="white"
          >
            <option value="">{METERING.CONTROLS.ALL_TENANTS}</option>
            {tenantOptions.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </Select>
        ) : null}

        {showSubTabs && subTab && onSubTabChange ? (
          <SegmentedTabBar
            options={[...METERING.SUB_TABS]}
            activeId={subTab}
            onChange={onSubTabChange}
          />
        ) : null}

        {showTopN && topN != null && onTopNChange ? (
          <Select
            size="sm"
            w="120px"
            value={topN}
            onChange={(e) => onTopNChange(Number(e.target.value) as MeteringTopN)}
            bg="white"
          >
            {METERING.TOP_N_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {METERING.CONTROLS.TOP_N_PREFIX} {n}
              </option>
            ))}
          </Select>
        ) : null}
      </HStack>

      <VStack align="flex-end" spacing={1}>
        {lastRefreshed ? (
          <HStack spacing={1}>
            <Box w={2} h={2} borderRadius="full" bg="green.400" />
            <Text fontSize="xs" color="gray.500" fontStyle="italic">
              {METERING.CONTROLS.LAST_REFRESHED_PREFIX} {lastRefreshed}
            </Text>
          </HStack>
        ) : null}
        {onRefresh ? (
          <Button
            size="xs"
            leftIcon={<RepeatIcon />}
            variant="ghost"
            onClick={onRefresh}
            isLoading={isRefreshing}
            color="gray.500"
          >
            {METERING.CONTROLS.REFRESH}
          </Button>
        ) : null}
      </VStack>
    </HStack>
  </VStack>
);

export default MeteringControls;
