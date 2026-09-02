import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  HStack,
  Select,
  Text,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { fetchTenantUsageById } from "../../services/usageSpendService";
import { INSTITUTION } from "../../config/constants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useUsageAndSpendData } from "../../hooks/useUsageAndSpendData";
import { billingPeriodValue } from "../../utils/usageSpendHelpers";
import type { TenantUsageDetail, TenantUsageItem } from "../../types/usageSpend";
import InstitutionUsageDetailPanel from "./InstitutionUsageDetailPanel";
import BillingMonthSelect from "./BillingMonthSelect";
import UsageSpendTenantDrawer from "./UsageSpendTenantDrawer";
import UsageSpendTenantTable from "./UsageSpendTenantTable";

interface UsageAndSpendTabProps {
  readonly scopeTenantId?: string | null;
  readonly isTenantView?: boolean;
  readonly tenantId?: string | null;
  readonly organisationLabel?: string | null;
  readonly refreshNonce?: number;
}

const UsageAndSpendTab: React.FC<UsageAndSpendTabProps> = ({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  organisationLabel = null,
  refreshNonce = 0,
}) => {
  const [filterTierId, setFilterTierId] = useState("");
  const [billingPeriod, setBillingPeriod] = useState(() => billingPeriodValue("current"));
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [selectedTenant, setSelectedTenant] = useState<TenantUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const detailRequestIdRef = useRef(0);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const { taskTypeNames } = useInferenceTypes();
  const enabledTaskTypesParam =
    taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const data = useUsageAndSpendData({
    scopeTenantId,
    isTenantView,
    tenantId,
    refreshNonce,
    filterTierId,
    taskTypeNames,
    billingPeriod,
  });

  const tenantDetail = isTenantView || data.isScoped ? (data.tenants[0] ?? null) : null;

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleTenantClick = useCallback(
    (row: TenantUsageItem) => {
      setSelectedTenantId(row.tenantId);
      onDetailOpen();
    },
    [onDetailOpen],
  );

  useEffect(() => {
    if (!isDetailOpen || !selectedTenantId) return;
    const requestId = ++detailRequestIdRef.current;
    setIsDetailLoading(true);
    fetchTenantUsageById(selectedTenantId, billingPeriod, enabledTaskTypesParam)
      .then((detail) => {
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(detail);
      })
      .catch(() => {
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(null);
      })
      .finally(() => {
        if (requestId === detailRequestIdRef.current) setIsDetailLoading(false);
      });
  }, [isDetailOpen, selectedTenantId, billingPeriod, enabledTaskTypesParam]);

  const handleDetailClose = useCallback(() => {
    detailRequestIdRef.current += 1;
    onDetailClose();
    setSelectedTenantId(null);
    setSelectedTenant(null);
    setIsDetailLoading(false);
  }, [onDetailClose]);

  if (tenantDetail) {
    return (
      <VStack align="stretch" spacing={5}>
        <InstitutionUsageDetailPanel
          detail={tenantDetail}
          organisationLabel={organisationLabel}
          isLoading={data.isTenantsLoading}
          billingPeriod={billingPeriod}
          onBillingPeriodChange={setBillingPeriod}
        />
      </VStack>
    );
  }

  return (
    <VStack align="stretch" spacing={5}>
      <HStack spacing={3} flexWrap="wrap" align="center">
        <BillingMonthSelect value={billingPeriod} onChange={setBillingPeriod} />
        <Select
          size="sm"
          w={{ base: "full", sm: "auto" }}
          minW={{ sm: "220px" }}
          maxW={{ sm: "280px" }}
          value={filterTierId}
          onChange={(e) => setFilterTierId(e.target.value)}
          borderRadius="full"
          bg="white"
          fontSize="13px"
          fontWeight="medium"
          borderColor="gray.300"
        >
          <option value="">Filter by tier · All tiers</option>
          {data.tiers.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </HStack>

      <UsageSpendTenantTable
        tenants={data.tenants}
        isLoading={data.isTenantsLoading}
        errorMessage={data.tenantsError}
        emptyMessage={`No ${INSTITUTION.toLowerCase()} usage data available.`}
        expanded={expanded}
        onToggleExpand={toggleExpand}
        onTenantClick={handleTenantClick}
      />

      <Text fontSize="12px" color="gray.500" lineHeight="1.6">
        Month filter scopes which institutions appear in this list. Budget and per–task-type
        usage are all-time — open an institution for the full breakdown.
      </Text>

      <UsageSpendTenantDrawer
        isOpen={isDetailOpen}
        onClose={handleDetailClose}
        detail={selectedTenant}
        isLoading={isDetailLoading}
        billingPeriod={billingPeriod}
        onBillingPeriodChange={setBillingPeriod}
      />
    </VStack>
  );
};

export default UsageAndSpendTab;
