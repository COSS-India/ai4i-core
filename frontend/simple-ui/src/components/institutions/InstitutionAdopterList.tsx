import { useMemo } from "react";
import { Badge, Center, HStack, Text, Tooltip } from "@chakra-ui/react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableSortState,
} from "../common/table";
import { InstitutionTenantRowActions } from "./InstitutionRowActions";
import {
  INSTITUTION,
  INSTITUTIONS,
  TENANT,
  TENANT_STATUS_LIST,
  formatTenantStatusLabel,
  getTenantStatusColorScheme,
} from "../../config/constants";
import { isDefaultTenant } from "../../utils/defaultTenant";
import { dash, fmtDate } from "../../utils/valueFormatters";
import type { TenantView } from "../../types/tenant";
import type { TenantTierAssignment } from "../../services/tierManagementService";
import { useTenantManagement } from "./hooks/useTenantManagement";
import {
  getTenantAvatarBg,
  getTenantInitials,
  resolveTenantTierName,
  type TierOption,
} from "./institutionDisplay";

type TenantManagement = ReturnType<typeof useTenantManagement>;

export function InstitutionAdopterList({
  tm,
  sortedTenants,
  tenantSort,
  isAdmin,
  tierOptions,
  tenantTierAssignmentsById,
  tierFilterOptions,
  handleTierFilterChange,
  openTenantPlan,
}: {
  tm: TenantManagement;
  sortedTenants: TenantView[];
  tenantSort: {
    sort: DataTableSortState;
    onSortChange: (next: DataTableSortState) => void;
  };
  isAdmin: boolean;
  tierOptions: TierOption[];
  tenantTierAssignmentsById: Map<string, TenantTierAssignment>;
  tierFilterOptions: TierOption[];
  handleTierFilterChange: (next: string) => void;
  openTenantPlan: (tenant: TenantView) => void;
}) {
  const tenantColumns = useMemo((): DataTableColumn<TenantView>[] => {
    return [
      {
        id: "organisation",
        header: INSTITUTION,
        thProps: { w: "420px", maxW: "420px" },
        tdProps: { maxW: "420px" },
        sortable: true,
        sortAccessor: (t) => t.organisation ?? "",
        cell: (t) => (
          <HStack spacing={3} minW={0}>
            <Center
              w={8}
              h={8}
              borderRadius="full"
              bg={getTenantAvatarBg(t.organisation)}
              color="white"
              fontSize="xs"
              fontWeight="bold"
              flexShrink={0}
            >
              {getTenantInitials(t.organisation)}
            </Center>
            <Tooltip
              label={t.organisation}
              placement="top"
              hasArrow
              openDelay={300}
            >
              <HStack spacing={2} minW={0} maxW="340px">
                <Text fontWeight="medium" fontSize="sm" isTruncated>
                  {t.organisation}
                </Text>
                {isDefaultTenant(t) && (
                  <Badge
                    colorScheme="purple"
                    fontSize="0.65rem"
                    flexShrink={0}
                    textTransform="none"
                  >
                    Default
                  </Badge>
                )}
              </HStack>
            </Tooltip>
          </HStack>
        ),
      },
      {
        id: "contact",
        header: "Contact",
        thProps: { w: "280px", maxW: "280px" },
        tdProps: { maxW: "280px" },
        sortable: true,
        sortAccessor: (t) => t.contact_name ?? "",
        cell: (t) => (
          <Tooltip
            label={dash(t.contact_name)}
            placement="top"
            hasArrow
            openDelay={300}
          >
            <Text fontSize="sm" isTruncated maxW="260px">
              {dash(t.contact_name)}
            </Text>
          </Tooltip>
        ),
      },
      {
        id: "email",
        header: "Email",
        sortable: true,
        sortAccessor: (t) => t.email ?? "",
        cell: (t) => dash(t.email),
      },
      {
        id: "status",
        header: "Status",
        cell: (t) => (
          <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
            {formatTenantStatusLabel(t.status)}
          </Badge>
        ),
      },
      // ADMIN-only: both tier queries are gated on `isAdmin`, so anyone else
      // would see a column of dashes reading as "no tier assigned".
      ...((isAdmin
        ? [
            {
              id: "tier",
              header: "Tier",
              thProps: { w: "180px", maxW: "180px" },
              tdProps: { maxW: "180px" },
              sortable: true,
              // Badge treatment mirrors the Service Registry "Tiers" column.
              truncate: false,
              cell: (t) => {
                const name = resolveTenantTierName(
                  t,
                  tierOptions,
                  tenantTierAssignmentsById,
                );
                if (!name) {
                  return (
                    <Text fontSize="sm" color="gray.400">
                      —
                    </Text>
                  );
                }
                return (
                  <Tooltip
                    label={name}
                    placement="top"
                    hasArrow
                    openDelay={300}
                  >
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={0.5}
                      maxW="100%"
                      isTruncated
                    >
                      {name}
                    </Badge>
                  </Tooltip>
                );
              },
            },
          ]
        : []) as DataTableColumn<TenantView>[]),
      {
        id: "created",
        header: "Onboarded",
        sortable: true,
        sortAccessor: (t) =>
          t.created_at ? new Date(t.created_at).getTime() : 0,
        cell: (t) => fmtDate(t.created_at),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (t) => (
          <InstitutionTenantRowActions
            tm={tm}
            tenant={t}
            onOpenPlan={openTenantPlan}
          />
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm, isAdmin, tierOptions, tenantTierAssignmentsById]);

  return (
          <DataTable
            layout="admin"
            items={sortedTenants}
            columns={tenantColumns}
            getRowKey={(t) => t.tenant_id}
            sort={tenantSort.sort}
            onSortChange={tenantSort.onSortChange}
            onRowClick={tm.handleViewTenant}
            isLoading={tm.isLoadingTenants}
            emptyMessage={`No ${INSTITUTIONS.toLowerCase()} found.`}
            noResultsMessage={`No ${INSTITUTIONS.toLowerCase()} match the current filters.`}
            unfilteredCount={tm.tenants.length}
            hasActiveFilters={
              tm.tenantFilterStatus !== "all" ||
              tm.tenantFilterTier !== TENANT.TIER_FILTER.ALL ||
              tm.tenantSearch.trim() !== ""
            }
            onClearFilters={() => {
              tm.setTenantFilterStatus("all");
              handleTierFilterChange(TENANT.TIER_FILTER.ALL);
              tm.setTenantSearch("");
            }}
            paginate="client"
            paginationPosition="bottom"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            search={{
              value: tm.tenantSearch,
              onChange: tm.setTenantSearch,
              placeholder: `Search by organisation or ${INSTITUTION.toLowerCase()} ID`,
              fields: ["organisation", "tenant_id"],
            }}
            filterDefs={[
              {
                id: "status",
                label: "Status",
                type: "select",
                param: "status",
                value: tm.tenantFilterStatus,
                onChange: tm.setTenantFilterStatus,
                width: { base: "full", sm: "200px" },
                options: [
                  { label: "All statuses", value: "all" },
                  ...TENANT_STATUS_LIST.map((s) => ({
                    label: formatTenantStatusLabel(s),
                    value: s,
                  })),
                ],
              },
              // ADMIN-only, for the same reason as the Tier column: without
              // the catalog there are no names to populate the options with.
              ...(isAdmin
                ? [
                    {
                      id: "tier",
                      label: "Tier",
                      // Filtered client-side — GET /tenants takes only `status`.
                      type: "select" as const,
                      value: tm.tenantFilterTier,
                      onChange: handleTierFilterChange,
                      width: { base: "full", sm: "200px" },
                      options: [
                        { label: "All tiers", value: TENANT.TIER_FILTER.ALL },
                        ...tierFilterOptions.map((tier) => ({
                          label: tier.name,
                          value: String(tier.id),
                        })),
                        {
                          label: "No tier assigned",
                          value: TENANT.TIER_FILTER.NONE,
                        },
                      ],
                    },
                  ]
                : []),
            ]}
          />
    );
}
