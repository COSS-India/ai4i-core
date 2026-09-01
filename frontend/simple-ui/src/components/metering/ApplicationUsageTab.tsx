import React, { useCallback, useRef, useState } from "react";
import {
  Alert,
  AlertIcon,
  Box,
  Flex,
  HStack,
  Text,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { METERING } from "../../config/meteringConstants";
import { INSTITUTION } from "../../config/constants";
import { useApplicationUsageData } from "../../hooks/useApplicationUsageData";
import { fetchApplicationUsageDetail } from "../../services/applicationUsageService";
import type {
  ApplicationUsageDetail,
  ApplicationUsageListItem,
} from "../../types/applicationUsage";
import ApplicationUsageDrawer from "./ApplicationUsageDrawer";
import ApplicationUsageSummaryPanel from "./ApplicationUsageSummaryPanel";
import ApplicationUsageTable from "./ApplicationUsageTable";

interface ApplicationUsageTabProps {
  readonly scopeTenantId?: string | null;
  readonly isTenantView?: boolean;
  readonly tenantId?: string | null;
  readonly organisationLabel?: string | null;
  readonly refreshNonce?: number;
}

const ApplicationUsageTab: React.FC<ApplicationUsageTabProps> = ({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  organisationLabel = null,
  refreshNonce = 0,
}) => {
  const scopedId = (isTenantView ? tenantId : scopeTenantId)?.trim() || null;
  const [selected, setSelected] = useState<ApplicationUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const detailRequestIdRef = useRef(0);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();

  const data = useApplicationUsageData({
    tenantId: scopedId,
    refreshNonce,
  });

  const copy = METERING.APPLICATION_USAGE;
  const orgName = organisationLabel?.trim() || null;

  const handleApplicationClick = useCallback(
    async (row: ApplicationUsageListItem) => {
      if (!scopedId) return;
      const requestId = ++detailRequestIdRef.current;
      onDetailOpen();
      setIsDetailLoading(true);
      try {
        const detail = await fetchApplicationUsageDetail(scopedId, row.applicationId);
        if (requestId !== detailRequestIdRef.current) return;
        setSelected(detail);
      } catch {
        if (requestId !== detailRequestIdRef.current) return;
        setSelected(null);
      } finally {
        if (requestId === detailRequestIdRef.current) setIsDetailLoading(false);
      }
    },
    [scopedId, onDetailOpen],
  );

  const handleDetailClose = useCallback(() => {
    detailRequestIdRef.current += 1;
    onDetailClose();
    setSelected(null);
    setIsDetailLoading(false);
  }, [onDetailClose]);

  if (!data.isScoped) {
    return (
      <Box py={10}>
        <Text color="gray.500" fontSize="sm" textAlign="center">
          {copy.SELECT_INSTITUTION}
        </Text>
      </Box>
    );
  }

  return (
    <VStack align="stretch" spacing={5}>
      {isTenantView ? (
        <Flex justify="space-between" align="center" gap={6} flexWrap="wrap">
          <HStack spacing="14px" align="center">
            <Box>
              <Text fontSize="18px" fontWeight="bold" lineHeight="1.2">
                {orgName || `My ${INSTITUTION}`}
              </Text>
              <Text fontSize="13px" color="gray.500">
                Application usage · lifetime totals
              </Text>
            </Box>
          </HStack>
        </Flex>
      ) : null}

      <Alert status="info" borderRadius="md" fontSize="sm">
        <AlertIcon />
        {copy.LIFETIME_NOTE}
      </Alert>

      <ApplicationUsageSummaryPanel
        summary={data.summary}
        isLoading={data.isSummaryLoading}
        error={data.summaryError}
      />

      <ApplicationUsageTable
        applications={data.applications}
        isLoading={data.isListLoading}
        errorMessage={data.listError}
        emptyMessage={copy.EMPTY}
        onApplicationClick={(row) => void handleApplicationClick(row)}
      />

      <Text fontSize="12px" color="gray.500" lineHeight="1.6">
        {copy.FOOTER}
      </Text>

      <ApplicationUsageDrawer
        isOpen={isDetailOpen}
        onClose={handleDetailClose}
        detail={selected}
        isLoading={isDetailLoading}
      />
    </VStack>
  );
};

export default ApplicationUsageTab;
