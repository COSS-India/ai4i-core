import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  FormControl,
  Input,
  HStack,
  Text,
  VStack,
  Alert,
  AlertIcon,
  AlertDescription,
  SimpleGrid,
  Checkbox,
  CheckboxGroup,
  Tooltip,
  Badge,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useApiKeyManagementTab, type ApiKeyTableRow } from "./hooks/useApiKeyManagementTab";
import { useApiKeyBudgetEdit } from "./hooks/useApiKeyBudgetEdit";
import { BUDGET_COPY, editBudgetForKey } from "../../config/budgetMessages";
import ApiKeyBulkBudgetModal from "./ApiKeyBulkBudgetModal";
import ApiKeyBudgetModal from "./ApiKeyBudgetModal";
import { RevokeBudgetBreakdown } from "./budgetVisuals";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { FiSlash, FiSliders } from "react-icons/fi";
import { EditIcon, ViewIcon } from "@chakra-ui/icons";
import {
  ApplicationEmptyState,
  ApplicationNoResults,
  EntityIdentity,
  InstitutionAllocationPanel,
  InstitutionAllocationSkeleton,
  StatusDot,
} from "./applicationSurface";
import DataTable, {
  DataTableActions,
  DEFAULT_PAGE_SIZE_OPTIONS,
  FieldLabel,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import ConfirmDialog from "../common/ConfirmDialog";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import FieldHint from "../common/FieldHint";
import {
  API_KEY,
  API_KEY_FILTER_STATUS_LIST,
  formatApiKeyDisplayStatusLabel,
  formatApiKeyFilterStatusLabel,
} from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";

function apiKeyStatusTone(
  status: string,
): "success" | "warning" | "danger" | "neutral" {
  if (status === API_KEY.DISPLAY_STATUS.ACTIVE) return "success";
  if (status === API_KEY.DISPLAY_STATUS.INACTIVE) return "warning";
  if (status === API_KEY.DISPLAY_STATUS.REVOKED) return "danger";
  return "neutral";
}

export type ApiKeyPageActions = {
  refresh: () => void;
  openBulk: () => void;
  bulkDisabled: boolean;
  refreshing: boolean;
};

export interface ApiKeyManagementTabProps {
  /** When true, tab is visible; used to fetch data when user switches to this tab */
  isActive?: boolean;
  /** Parent can trigger refresh after keys are created on another tab */
  onRegisterRefresh?: (refresh: () => Promise<void>) => void;
  onCreate?: () => void;
  onBindPageActions?: (actions: ApiKeyPageActions) => void;
}

export default function ApiKeyManagementTab({
  isActive = false,
  onRegisterRefresh,
  onCreate,
  onBindPageActions,
}: ApiKeyManagementTabProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { user } = useAuth();

  const mgmt = useApiKeyManagementTab({
    user: user ?? null,
  });

  const bulkBudget = useApiKeyBudgetEdit({
    tenantId: user?.tenant_id,
    applications: mgmt.applications,
    initialApplicationId:
      mgmt.filterApplication !== "all" ? mgmt.filterApplication : undefined,
    onSaved: mgmt.handleFetchAllApiKeys,
  });
  const singleBudget = useApiKeyBudgetEdit({
    tenantId: user?.tenant_id,
    applications: mgmt.applications,
    onSaved: mgmt.handleFetchAllApiKeys,
  });

  const keySortAccessors = useMemo(
    () => ({
      key_name: (a: ApiKeyTableRow) => a.key_name ?? "",
      application: (a: ApiKeyTableRow) =>
        a.application_name ?? a.application_id ?? "",
      budget: (a: ApiKeyTableRow) =>
        a.allocated_percentage ?? a.allocated_budget ?? -1,
      created: (a: ApiKeyTableRow) =>
        a.created_at ? new Date(a.created_at).getTime() : 0,
      expires: (a: ApiKeyTableRow) =>
        a.expires_at ? new Date(a.expires_at).getTime() : Number.POSITIVE_INFINITY,
    }),
    [],
  );
  const keySort = useDeferredColumnSort("key_name", keySortAccessors);

  const sortedApiKeys = useMemo(
    () => keySort.apply(mgmt.filteredApiKeys),
    [mgmt.filteredApiKeys, keySort],
  );

  const hasActiveFilters =
    mgmt.filterApplication !== "all" ||
    mgmt.filterPermission !== "all" ||
    mgmt.filterActive !== "all" ||
    mgmt.keyNameSearch.trim() !== "";

  const openBulkBudget = bulkBudget.open;
  const openSingleKeyBudget = singleBudget.openForKey;
  const refreshApiKeys = mgmt.handleFetchAllApiKeys;
  const apiKeyApplicationCount = mgmt.applications.length;
  const apiKeysRefreshing = mgmt.isLoadingAllApiKeys;

  const apiKeyColumns = useMemo((): DataTableColumn<ApiKeyTableRow>[] => {
    return [
      {
        id: "key_name",
        header: "Key",
        sortable: true,
        sortAccessor: (key) => key.key_name ?? "",
        cell: (key) => (
          <EntityIdentity name={key.key_name || "API key"} meta={key.api_key} />
        ),
      },
      {
        id: "application",
        header: "Application",
        sortable: true,
        sortAccessor: (key) => key.application_name ?? key.application_id ?? "",
        cell: (key) => (
          <Text fontSize="sm">{key.application_name ?? key.application_id ?? "—"}</Text>
        ),
      },
      {
        id: "permissions",
        header: "Permissions",
        thProps: { display: { base: "none", xl: "table-cell" } },
        tdProps: { display: { base: "none", xl: "table-cell" } },
        cell: (key) => {
          const count = mgmt.visiblePermissionsForKey(key).length;
          return (
            <Text fontSize="sm" color="ink.600">
              {count === 0 ? "—" : `${count} ${count === 1 ? "permission" : "permissions"}`}
            </Text>
          );
        },
      },
      {
        id: "budget",
        header: "Allocation",
        sortable: true,
        sortAccessor: (key) =>
          key.allocated_percentage ?? key.allocated_budget ?? -1,
        cell: (key) => {
          const pctLabel = mgmt.formatBudgetPct(key);
          if (pctLabel === "—") {
            return <Text fontSize="sm" color="ink.500">—</Text>;
          }
          return (
            <Box>
              <Text fontSize="sm" fontWeight="700" color="ink.800">
                {pctLabel}
              </Text>
              {key.allocated_budget != null && (
                <Text fontSize="xs" color="ink.500">
                  {formatSpendMoney(key.allocated_budget, "INR")}
                </Text>
              )}
            </Box>
          );
        },
      },
      {
        id: "status",
        header: "Status",
        cell: (key) => {
          const displayStatus = mgmt.resolveKeyDisplayStatus(key);
          const reason = mgmt.getKeyInactiveReason(key) ?? mgmt.getKeyRevokedReason(key);
          const indicator = (
            <StatusDot
              label={formatApiKeyDisplayStatusLabel(displayStatus)}
              tone={apiKeyStatusTone(displayStatus)}
            />
          );
          return reason ? (
            <Tooltip label={reason} placement="top" hasArrow openDelay={300}>
              <Box as="span" tabIndex={0} display="inline-flex">
                {indicator}
              </Box>
            </Tooltip>
          ) : (
            indicator
          );
        },
      },
      {
        id: "created",
        header: "Created",
        thProps: { display: { base: "none", xl: "table-cell" } },
        tdProps: { display: { base: "none", xl: "table-cell" } },
        sortable: true,
        sortAccessor: (key) =>
          key.created_at ? new Date(key.created_at).getTime() : 0,
        cell: (key) => (
          <Text fontSize="sm">
            {key.created_at ? new Date(key.created_at).toLocaleDateString() : "—"}
          </Text>
        ),
      },
      {
        id: "expires",
        header: "Expiry",
        sortable: true,
        sortAccessor: (key) =>
          key.expires_at
            ? new Date(key.expires_at).getTime()
            : Number.POSITIVE_INFINITY,
        cell: (key) => (
          <Text fontSize="sm">
            {key.expires_at ? new Date(key.expires_at).toLocaleDateString() : "Never"}
          </Text>
        ),
      },
      {
        id: "actions",
        header: "Actions",
        align: "right",
        width: "176px",
        minWidth: "176px",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (key) => (
          <DataTableActions
            justify="flex-end"
            actions={[
              {
                id: "view",
                label: "View API key",
                tooltip: "View",
                icon: <ViewIcon />,
                onClick: () => mgmt.handleOpenViewModal(key),
              },
              {
                id: "edit",
                label: "Update API key",
                tooltip: mgmt.isKeyEffectivelyActive(key)
                  ? "Update key"
                  : mgmt.isKeyRevocable(key)
                    ? "Only effectively active API keys can be updated."
                    : "This API key has been revoked and cannot be updated.",
                icon: <EditIcon />,
                disabled: !mgmt.isKeyEffectivelyActive(key),
                onClick: () => mgmt.handleOpenUpdateModal(key),
              },
              {
                id: "budget",
                label: "Edit budget",
                tooltip: !key.application_id
                  ? BUDGET_COPY.keyHasNoApplication
                  : mgmt.isKeyEffectivelyActive(key)
                    ? BUDGET_COPY.editBudget
                    : mgmt.isKeyRevocable(key)
                      ? "Only effectively active API keys can have their budget edited."
                      : "This API key has been revoked and cannot have its budget edited.",
                "aria-label": editBudgetForKey(key.key_name),
                icon: <FiSliders />,
                disabled: !key.application_id || !mgmt.isKeyEffectivelyActive(key),
                onClick: () => {
                  if (key.application_id) {
                    openSingleKeyBudget(key.application_id, key.id, key.key_name);
                  }
                },
              },
              {
                id: "revoke",
                label: "Revoke API key",
                tooltip: mgmt.isKeyRevocable(key) ? "Revoke key" : "Already revoked",
                icon: <FiSlash />,
                color: "red.500",
                hoverColor: "red.600",
                hoverBg: "red.50",
                disabled: !mgmt.isKeyRevocable(key),
                onClick: () => mgmt.handleOpenRevokeModal(key),
              },
            ]}
          />
        ),
      },
    ];
  }, [mgmt, openSingleKeyBudget]);

  useEffect(() => {
    onRegisterRefresh?.(mgmt.handleFetchAllApiKeys);
  }, [onRegisterRefresh, mgmt.handleFetchAllApiKeys]);

  useEffect(() => {
    onBindPageActions?.({
      refresh: () => void refreshApiKeys(),
      openBulk: () => openBulkBudget(),
      bulkDisabled: apiKeyApplicationCount === 0,
      refreshing: apiKeysRefreshing,
    });
  }, [
    apiKeyApplicationCount,
    apiKeysRefreshing,
    onBindPageActions,
    openBulkBudget,
    refreshApiKeys,
  ]);

  useEffect(() => {
    if (isActive) {
      void mgmt.handleFetchAllApiKeys({ silent: true });
    }
  }, [isActive, mgmt.handleFetchAllApiKeys]);

  const viewKey = mgmt.selectedKeyForView;

  return (
    <>
      <FormDrawer
        isOpen={Boolean(mgmt.isViewModalOpen && viewKey)}
        onClose={mgmt.handleCloseViewModal}
        title={viewKey?.key_name || "API Key"}
        description="View this key's application, budget, and permissions."
        footer={
          <FormActions
            hideSubmit
            cancelLabel="Close"
            onCancel={mgmt.handleCloseViewModal}
            pt={0}
          />
        }
      >
        {viewKey ? (
          <>
      <FormSection title="API Key">
        <ReadOnlyField label="Key Name">{viewKey.key_name}</ReadOnlyField>
        <ReadOnlyField label="Key ID">
          <Text fontSize="sm" fontFamily="mono" color="ink.700" wordBreak="break-all">
            {mgmt.formatKeyId(viewKey)}
          </Text>
        </ReadOnlyField>
        <ReadOnlyField label="Application">
          {viewKey.application_name ?? viewKey.application_id ?? "—"}
        </ReadOnlyField>
        <ReadOnlyField label="Permissions" fullWidth>
          {(() => {
            const visiblePerms = mgmt.visiblePermissionsForKey(viewKey);
            return visiblePerms.length > 0 ? (
              <HStack flexWrap="wrap" spacing={2}>
                {visiblePerms.map((perm) => (
                  <Badge key={String(perm)} colorScheme="gray" fontSize="xs" px={2} py={0.5}>
                    {mgmt.formatPermission(perm)}
                  </Badge>
                ))}
              </HStack>
            ) : (
              <Text fontSize="sm" color="ink.500">
                No permissions assigned
              </Text>
            );
          })()}
        </ReadOnlyField>
      </FormSection>
      <FormSection title="Record">
        <ReadOnlyField label="Budget">
          <Text fontSize="sm" color="ink.800">
            {mgmt.formatBudgetPct(viewKey)}
          </Text>
          {viewKey.allocated_budget != null &&
            mgmt.formatBudgetPct(viewKey) !== "—" && (
              <Text fontSize="sm" color="ink.500">
                {formatSpendMoney(viewKey.allocated_budget, "INR")}
              </Text>
            )}
        </ReadOnlyField>
        <ReadOnlyField label="Status">
          <StatusDot
            label={formatApiKeyDisplayStatusLabel(mgmt.resolveKeyDisplayStatus(viewKey))}
            tone={apiKeyStatusTone(mgmt.resolveKeyDisplayStatus(viewKey))}
          />
          {(mgmt.getKeyInactiveReason(viewKey) ?? mgmt.getKeyRevokedReason(viewKey)) && (
            <Text fontSize="xs" color="ink.500" mt={2}>
              {mgmt.getKeyInactiveReason(viewKey) ?? mgmt.getKeyRevokedReason(viewKey)}
            </Text>
          )}
        </ReadOnlyField>
        <ReadOnlyField label="Created At">
          {viewKey.created_at
            ? new Date(viewKey.created_at).toLocaleString()
            : "—"}
        </ReadOnlyField>
        {viewKey.expires_at ? (
          <ReadOnlyField label="Expires At">
            {new Date(viewKey.expires_at).toLocaleString()}
          </ReadOnlyField>
        ) : null}
        {viewKey.last_used ? (
          <ReadOnlyField label="Last Used">
            {new Date(viewKey.last_used).toLocaleString()}
          </ReadOnlyField>
        ) : null}
      </FormSection>
          </>
        ) : null}
      </FormDrawer>
      <VStack align="stretch" spacing={5}>
        {mgmt.isLoadingAllApiKeys && mgmt.allApiKeys.length === 0 ? (
          <InstitutionAllocationSkeleton />
        ) : mgmt.allocationOverview.comparable &&
          mgmt.allocationOverview.allocatedPct != null &&
          mgmt.allocationOverview.availablePct != null ? (
          <InstitutionAllocationPanel
            applicationCount={mgmt.allocationOverview.keyCount}
            countLabel="API keys"
            countSub="Across applications"
            allocatedPct={mgmt.allocationOverview.allocatedPct}
            availablePct={mgmt.allocationOverview.availablePct}
            institutionBudget={mgmt.allocationOverview.pool}
            currency="INR"
            overAllocated={mgmt.allocationOverview.allocatedPct > 100 + 1e-6}
            allocatedCaption="assigned to active keys"
            availableCaption="unassigned in applications"
            overMessage="Allocation exceeds the application budgets."
          />
        ) : (
          <InstitutionAllocationPanel
            applicationCount={mgmt.allocationOverview.keyCount}
            countLabel="API keys"
            countSub="Across applications"
            figures="amount"
            allocatedAmount={mgmt.allocationOverview.allocatedAmount}
            institutionBudget={0}
            currency="INR"
            showAvailable={false}
            showBar={false}
            allocatedCaption="assigned to active keys"
          />
        )}
      <DataTable
            layout="admin"
            toolbarAttached
            showRowChevron={false}
            items={sortedApiKeys}
            columns={apiKeyColumns}
            getRowKey={(key) =>
              key.api_key ?? `id-${key.id ?? ""}-${key.application_id ?? ""}-${key.key_name}`
            }
            onRowClick={mgmt.handleOpenViewModal}
            isLoading={mgmt.isLoadingAllApiKeys && mgmt.allApiKeys.length === 0}
            loadingMessage="Loading API keys..."
            emptyContent={
              hasActiveFilters ? (
                <ApplicationNoResults
                  onClear={mgmt.handleResetFilters}
                  title="No matching API keys"
                  body="Try another name or filter."
                  actionLabel="Clear filters"
                />
              ) : (
                <ApplicationEmptyState
                  onCreate={() => onCreate?.()}
                  title="No API keys yet"
                  body="Create an API key to grant application access."
                  actionLabel="Create API Key"
                />
              )
            }
            emptyMessage="No API keys yet."
            noResultsMessage="No API keys match the current filters."
            unfilteredCount={mgmt.visibleApiKeysCount}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={mgmt.handleResetFilters}
            sort={keySort.sort}
            onSortChange={keySort.onSortChange}
            paginate="client"
            paginationPosition="bottom"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            search={{
              label: "Search API keys",
              hideLabel: true,
              value: mgmt.keyNameSearch,
              onChange: mgmt.setKeyNameSearch,
              placeholder: "Search API keys...",
              fields: ["key_name"],
            }}
            filterDefs={[
              {
                id: "application",
                label: "Application",
                hideLabel: true,
                type: "select",
                param: "application_id",
                value: mgmt.filterApplication,
                onChange: mgmt.setFilterApplication,
                options: [
                  { label: "All Applications", value: "all" },
                  ...mgmt.applications.map((app) => ({
                    label: app.name,
                    value: app.application_id,
                  })),
                ],
              },
              {
                id: "permission",
                label: "Permission",
                hideLabel: true,
                type: "select",
                param: "permission",
                value: mgmt.filterPermission,
                onChange: mgmt.setFilterPermission,
                options: [
                  { label: "All Permissions", value: "all" },
                  ...mgmt.permissionFilterOptions.map((perm) => ({
                    label: mgmt.formatPermission(perm.name),
                    value: perm.name,
                  })),
                ],
              },
              {
                id: "status",
                label: "Status",
                hideLabel: true,
                type: "select",
                param: "status",
                value: mgmt.filterActive,
                onChange: mgmt.setFilterActive,
                options: [
                  { label: "All", value: API_KEY.FILTER_STATUS.ALL },
                  ...API_KEY_FILTER_STATUS_LIST.map((s) => ({
                    label: formatApiKeyFilterStatusLabel(s),
                    value: s,
                  })),
                ],
              },
            ]}
          />
      </VStack>

      <FormDrawer
        isOpen={mgmt.isUpdateModalOpen}
        onClose={mgmt.handleCloseUpdateModal}
        title="Update API Key"
        description="Change this key's name and permissions."
        footer={
          <FormActions
            submitLabel="Save Changes"
            onCancel={mgmt.handleCloseUpdateModal}
            onSubmit={mgmt.handleUpdateApiKey}
            isLoading={mgmt.isUpdating}
            isDisabled={
              !(mgmt.updateFormData.key_name ?? "").trim() ||
              !(mgmt.updateFormData.permissions?.length ?? 0)
            }
            loadingText="Saving..."
            justify="space-between"
            pt={0}
          />
        }
      >
        <VStack spacing={4} align="stretch">
              <FormControl isRequired>
                <FieldLabel>Key Name</FieldLabel>
                <Input
                  value={mgmt.updateFormData.key_name || ""}
                  onChange={(e) =>
                    mgmt.setUpdateFormData({ ...mgmt.updateFormData, key_name: e.target.value })
                  }
                  bg="white"
                />
              </FormControl>
              <FormControl isRequired>
                <FieldLabel>Permissions</FieldLabel>
                {mgmt.permissionFilterOptions.length > 0 ? (
                  <Box
                    borderWidth="1px"
                    borderRadius="md"
                    p={4}
                    bg="white"
                    maxH="300px"
                    overflowY="auto"
                  >
                    <CheckboxGroup
                      value={mgmt.updateFormData.permissions || []}
                      onChange={(values) =>
                        mgmt.setUpdateFormData({
                          ...mgmt.updateFormData,
                          permissions: values as string[],
                        })
                      }
                    >
                      <SimpleGrid columns={2} spacing={3}>
                        {mgmt.permissionFilterOptions.map((perm) => (
                          <Checkbox key={perm.name} value={perm.name} colorScheme="blue">
                            <Text fontSize="sm">{mgmt.formatPermission(perm.name)}</Text>
                          </Checkbox>
                        ))}
                      </SimpleGrid>
                    </CheckboxGroup>
                  </Box>
                ) : (
                  <Alert status="info" borderRadius="md">
                    <AlertIcon />
                    <AlertDescription>
                      Click &quot;Load Permissions&quot; in the Permissions tab to view available
                      permissions
                    </AlertDescription>
                  </Alert>
                )}
                <FieldHint>{FIELD_HINTS.apiKey.permissions.helper}</FieldHint>
              </FormControl>
              {mgmt.selectedKeyForUpdate?.api_key && (
                <Text fontSize="xs" color="ink.500">
                  Key: {mgmt.selectedKeyForUpdate.api_key.slice(0, 8)}…
                  {mgmt.selectedKeyForUpdate.api_key.slice(-4)}
                </Text>
              )}
        </VStack>
      </FormDrawer>

      <ConfirmDialog
        isOpen={mgmt.isRevokeModalOpen}
        onClose={mgmt.handleCloseRevokeModal}
        onConfirm={mgmt.handleRevokeApiKey}
        title={
          mgmt.keyToRevoke?.key_name
            ? `Revoke ${mgmt.keyToRevoke.key_name}`
            : "Revoke API Key"
        }
        body={
          <VStack align="stretch" spacing={4}>
            <Text fontSize="sm" color="ink.700" lineHeight="1.5">
              Revoking <Text as="b">{mgmt.keyToRevoke?.key_name}</Text> stops it from working
              immediately. This can&apos;t be undone.
            </Text>
            <RevokeBudgetBreakdown
              status={mgmt.revokeBudget?.status ?? "loading"}
              allocated={
                mgmt.revokeBudget?.status === "ready" ? mgmt.revokeBudget.allocated : undefined
              }
              consumed={
                mgmt.revokeBudget?.status === "ready" ? mgmt.revokeBudget.consumed : undefined
              }
              unused={
                mgmt.revokeBudget?.status === "ready" ? mgmt.revokeBudget.unused : undefined
              }
              applicationName={
                mgmt.revokeBudget?.status === "ready"
                  ? mgmt.revokeBudget.applicationName
                  : undefined
              }
            />
          </VStack>
        }
        confirmLabel="Revoke API Key"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={mgmt.isRevoking}
        isConfirmDisabled={mgmt.revokeBudget?.status === "loading"}
        confirmLoadingText="Revoking..."
        leastDestructiveRef={cancelRef}
      />

      <ApiKeyBudgetModal
        isOpen={singleBudget.isOpen}
        onClose={singleBudget.close}
        isLoading={singleBudget.isLoading}
        isSaving={singleBudget.isSaving}
        banner={singleBudget.banner}
        applicationName={singleBudget.applicationName}
        applicationBudget={singleBudget.applicationBudget}
        applicationBudgetUnset={singleBudget.applicationBudgetUnset}
        liveTotalPct={singleBudget.liveTotalPct}
        rows={singleBudget.rows}
        focusedKeyId={singleBudget.focusedKeyId}
        focusedKeyName={singleBudget.focusedKeyName}
        onPctChange={singleBudget.onPctChange}
        onPctBoundHit={singleBudget.onPctBoundHit}
        onSave={() => void singleBudget.save()}
        canSave={singleBudget.canSave}
      />

      <ApiKeyBulkBudgetModal
        isOpen={bulkBudget.isOpen}
        onClose={bulkBudget.close}
        isLoading={bulkBudget.isLoading}
        isSaving={bulkBudget.isSaving}
        banner={bulkBudget.banner}
        applications={bulkBudget.applications}
        selectedApplicationId={bulkBudget.selectedApplicationId}
        onApplicationChange={bulkBudget.onApplicationChange}
        applicationName={bulkBudget.applicationName}
        applicationBudget={bulkBudget.applicationBudget}
        applicationBudgetUnset={bulkBudget.applicationBudgetUnset}
        liveTotalPct={bulkBudget.liveTotalPct}
        rows={bulkBudget.rows}
        onPctChange={bulkBudget.onPctChange}
        onPctBoundHit={bulkBudget.onPctBoundHit}
        onAmountChange={bulkBudget.onAmountChange}
        onSave={() => void bulkBudget.save()}
        canSave={bulkBudget.canSave}
      />
    </>
  );
}
