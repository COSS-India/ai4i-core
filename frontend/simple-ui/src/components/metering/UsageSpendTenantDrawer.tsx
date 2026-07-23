import {
  Box,
  Center,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  HStack,
  Select,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import { billingPeriodLabel, type BillingPeriodKey } from "../../utils/usageSpendHelpers";
import type { TenantUsageDetail } from "../../types/usageSpend";
import SpendByTaskTypeTable from "./SpendByTaskTypeTable";
import { BudgetCell, TenantAvatar, TierBadge } from "./UsageSpendCells";

interface UsageSpendTenantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  detail: TenantUsageDetail | null;
  isLoading: boolean;
  /** Value shown in the period selector (may be pending while loading). */
  periodKey: BillingPeriodKey;
  /** Period that `detail` was fetched for — used for the spend section label. */
  loadedPeriodKey: BillingPeriodKey;
  onPeriodChange: (periodKey: BillingPeriodKey) => void;
}

const UsageSpendTenantDrawer: React.FC<UsageSpendTenantDrawerProps> = ({
  isOpen,
  onClose,
  detail,
  isLoading,
  periodKey,
  loadedPeriodKey,
  onPeriodChange,
}) => {
  const hasMultiTier = (detail?.tierBreakdown?.length ?? 0) > 1;
  const periodLabel = billingPeriodLabel(loadedPeriodKey);

  let body: React.ReactNode = null;
  if (isLoading && !detail) {
    body = (
      <Center py={12}>
        <Spinner color="blue.500" />
      </Center>
    );
  } else if (detail) {
    body = (
      <VStack align="stretch" spacing={5}>
        <HStack spacing="11px">
          <TenantAvatar name={detail.tenantName} size="md" />
          <Text fontSize="16px" fontWeight="bold">
            {detail.tenantName}
          </Text>
          <TierBadge label={detail.tier} />
        </HStack>

        <FormControl>
          <Text
            fontSize="11px"
            letterSpacing="0.04em"
            color="gray.600"
            fontWeight="semibold"
            mb={2}
          >
            {METERING.USAGE_SPEND.BILLING_PERIOD}
          </Text>
          <Select
            size="sm"
            value={periodKey}
            onChange={(e) => onPeriodChange(e.target.value as BillingPeriodKey)}
            borderRadius="8px"
            bg="white"
            maxW="220px"
            isDisabled={isLoading}
          >
            <option value="current">{METERING.USAGE_SPEND.CURRENT_MONTH}</option>
            <option value="last">{METERING.USAGE_SPEND.LAST_MONTH}</option>
          </Select>
        </FormControl>

        <Box>
          <Text fontSize="11px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb="10px">
            BUDGET
          </Text>
          <Box bg="gray.50" borderRadius="10px" p="16px 18px" opacity={isLoading ? 0.55 : 1}>
            <BudgetCell
              limit={detail.budget.limit}
              spent={detail.budget.spent}
              remaining={detail.budget.remaining}
              percentageUsed={detail.budget.percentageUsed}
              currency={detail.currency}
            />
          </Box>
        </Box>

        <Box position="relative" opacity={isLoading ? 0.55 : 1}>
          {isLoading ? (
            <Center position="absolute" inset={0} zIndex={1}>
              <Spinner color="blue.500" size="sm" />
            </Center>
          ) : null}
          <Text fontSize="11px" letterSpacing="0.04em" color="gray.600" fontWeight="semibold" mb="10px">
            SPEND BY MODEL TASK TYPE — {periodLabel}
          </Text>
          <SpendByTaskTypeTable
            tierBreakdown={detail.tierBreakdown ?? []}
            totalSpend={detail.spend}
            currency={detail.currency}
          />
          {hasMultiTier ? (
            <Text fontSize="11.5px" color="gray.500" lineHeight="1.5" mt="10px">
              Grouped by tier since this tenant changed tier during the period — spend and usage
              above the group total are cumulative across all tiers.
            </Text>
          ) : null}
        </Box>
      </VStack>
    );
  }

  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
      <DrawerOverlay bg="rgba(15,18,25,0.4)" />
      <DrawerContent maxW="640px">
        <DrawerCloseButton top={4} right={4} />
        <DrawerHeader fontSize="17px" fontWeight="bold" pb={2}>
          Tenant Spend Details
        </DrawerHeader>
        <DrawerBody pb={10}>{body}</DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default UsageSpendTenantDrawer;
