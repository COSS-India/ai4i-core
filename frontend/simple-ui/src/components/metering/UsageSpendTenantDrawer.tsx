import {
  Center,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
  HStack,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { METERING } from "../../config/meteringConstants";
import type { TenantUsageDetail } from "../../types/usageSpend";
import { InstitutionUsageDetailContent } from "./InstitutionUsageDetailPanel";
import { TenantAvatar, TierBadge } from "./UsageSpendCells";

interface UsageSpendTenantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  detail: TenantUsageDetail | null;
  isLoading: boolean;
  billingPeriod: string;
  onBillingPeriodChange: (value: string) => void;
}

const UsageSpendTenantDrawer: React.FC<UsageSpendTenantDrawerProps> = ({
  isOpen,
  onClose,
  detail,
  isLoading,
  billingPeriod,
  onBillingPeriodChange,
}) => {
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

        <InstitutionUsageDetailContent
          detail={detail}
          isLoading={isLoading}
          billingPeriod={billingPeriod}
          onBillingPeriodChange={onBillingPeriodChange}
        />
      </VStack>
    );
  }

  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
      <DrawerOverlay bg="rgba(15,18,25,0.4)" />
      <DrawerContent maxW="640px">
        <DrawerCloseButton top={4} right={4} />
        <DrawerHeader fontSize="17px" fontWeight="bold" pb={2}>
          {METERING.USAGE_SPEND.TENANT_DETAIL_TITLE}
        </DrawerHeader>
        <DrawerBody pb={10}>{body}</DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default UsageSpendTenantDrawer;
