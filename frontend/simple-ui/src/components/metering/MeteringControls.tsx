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
import type { MeteringTopN, MeteringWindow } from "../../types/metering";
import MeteringSubTabBar, { type MeteringSubTab } from "./MeteringSubTabBar";

const WINDOW_OPTIONS: { value: MeteringWindow; label: string }[] = [
  { value: "1h", label: "Last 1 hour" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

const TOP_N_OPTIONS: MeteringTopN[] = [5, 10, 25];

interface MeteringControlsProps {
  window: MeteringWindow;
  onWindowChange: (w: MeteringWindow) => void;
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
  window,
  onWindowChange,
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
      {WINDOW_OPTIONS.map((opt) => (
        <Button
          key={opt.value}
          onClick={() => onWindowChange(opt.value)}
          colorScheme={window === opt.value ? "orange" : "gray"}
          variant={window === opt.value ? "solid" : "outline"}
          fontWeight={window === opt.value ? "semibold" : "normal"}
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
            <option value="">All Tenants</option>
            {tenantOptions.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </Select>
        ) : null}

        {showSubTabs && subTab && onSubTabChange ? (
          <MeteringSubTabBar activeTab={subTab} onChange={onSubTabChange} />
        ) : null}

        {showTopN && topN != null && onTopNChange ? (
          <Select
            size="sm"
            w="120px"
            value={topN}
            onChange={(e) => onTopNChange(Number(e.target.value) as MeteringTopN)}
            bg="white"
          >
            {TOP_N_OPTIONS.map((n) => (
              <option key={n} value={n}>
                Top {n}
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
              Last refreshed: {lastRefreshed}
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
            Refresh
          </Button>
        ) : null}
      </VStack>
    </HStack>
  </VStack>
);

export default MeteringControls;
