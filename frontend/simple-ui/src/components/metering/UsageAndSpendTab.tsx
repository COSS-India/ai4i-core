import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  HStack,
  Select,
  Text,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { fetchTenantUsageById } from "../../services/usageSpendService";
import { METERING } from "../../config/meteringConstants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useUsageAndSpendData } from "../../hooks/useUsageAndSpendData";
import type { MeteringPeriod } from "../../types/metering";
import type { TenantUsageItem } from "../../types/usageSpend";
import { formatPeriodTitle } from "../../utils/meteringFormatters";
import InstitutionUsageDetailPanel from "./InstitutionUsageDetailPanel";
import MeteringAsyncState from "./MeteringAsyncState";
import UsageSpendTenantDrawer from "./UsageSpendTenantDrawer";
import UsageSpendTenantTable from "./UsageSpendTenantTable";

interface UsageAndSpendTabProps {
  readonly period: MeteringPeriod;
  readonly scopeTenantId?: string | null;
  readonly isTenantView?: boolean;
  readonly tenantId?: string | null;
  readonly organisationLabel?: string | null;
  readonly refreshNonce?: number;
}

const UsageAndSpendTab: React.FC<UsageAndSpendTabProps> = ({
  period,
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  organisationLabel = null,
  refreshNonce = 0,
}) => {
  const [filterTierId, setFilterTierId] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [selectedTenant, setSelectedTenant] = useState<TenantUsageItem | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const detailRequestIdRef = useRef(0);
  const selectedTenantRowRef = useRef<TenantUsageItem | null>(null);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const { taskTypeNames } = useInferenceTypes();
  const enabledTaskTypesParam =
    taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const data = useUsageAndSpendData({
    scopeTenantId,
    isTenantView,
    period,
    tenantId,
    refreshNonce,
    filterTierId,
    taskTypeNames,
  });

  const periodTitle = formatPeriodTitle(period);
  const isScopedView = isTenantView || data.isScoped;
  const tenantDetail = isScopedView ? (data.tenants[0] ?? null) : null;

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
      selectedTenantRowRef.current = row;
      setSelectedTenantId(row.tenantId);
      setSelectedTenant(null);
      onDetailOpen();
    },
    [onDetailOpen],
  );

  useEffect(() => {
    if (!isDetailOpen || !selectedTenantId) return;
    const requestId = ++detailRequestIdRef.current;
    setIsDetailLoading(true);
    fetchTenantUsageById(selectedTenantId, period, enabledTaskTypesParam)
      .then((detail) => {
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(detail);
      })
      .catch(() => {
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(selectedTenantRowRef.current);
      })
      .finally(() => {
        if (requestId === detailRequestIdRef.current) setIsDetailLoading(false);
      });
  }, [isDetailOpen, selectedTenantId, period, enabledTaskTypesParam]);

  const handleDetailClose = useCallback(() => {
    detailRequestIdRef.current += 1;
    onDetailClose();
    setSelectedTenantId(null);
    setSelectedTenant(null);
    selectedTenantRowRef.current = null;
    setIsDetailLoading(false);
  }, [onDetailClose]);

  // A scoped viewer never falls through to the Adopter layout, even while the
  // period's detail is loading or after it fails.
  if (isScopedView) {
    return (
      <MeteringAsyncState
        isLoading={!tenantDetail && data.isTenantsLoading}
        isEmpty={!tenantDetail}
        errorMessage={tenantDetail ? null : data.tenantsError}
        emptyMessage={METERING.EMPTY.PERIOD}
      >
        {tenantDetail ? (
          <VStack align="stretch" spacing={5}>
            <InstitutionUsageDetailPanel
              detail={tenantDetail}
              periodTitle={periodTitle}
              organisationLabel={organisationLabel}
              isLoading={data.isTenantsLoading}
            />
          </VStack>
        ) : null}
      </MeteringAsyncState>
    );
  }

  return (
    <VStack align="stretch" spacing={5}>
      <HStack spacing={3} flexWrap="wrap" align="center">
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
        emptyMessage={METERING.EMPTY.PERIOD}
        expanded={expanded}
        onToggleExpand={toggleExpand}
        onTenantClick={handleTenantClick}
      />

      <Text fontSize="12px" color="gray.500" lineHeight="1.6">
        {METERING.USAGE_SPEND.TABLE_NOTE}
      </Text>

      <UsageSpendTenantDrawer
        isOpen={isDetailOpen}
        onClose={handleDetailClose}
        detail={selectedTenant}
        periodTitle={periodTitle}
        isLoading={isDetailLoading}
      />
    </VStack>
  );
};

export default UsageAndSpendTab;
