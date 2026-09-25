import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
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
import ApiKeyBulkBudgetModal from "./ApiKeyBulkBudgetModal";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import { FiSlash } from "react-icons/fi";
import { EditIcon } from "@chakra-ui/icons";
import DataTable, {
  DataTableActions,
  DEFAULT_PAGE_SIZE_OPTIONS,
  FieldLabel,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import StandardModal from "../common/StandardModal";
import ConfirmDialog from "../common/ConfirmDialog";
import FormActions from "../common/FormActions";
import ReadOnlyField from "../common/ReadOnlyField";
import FieldHint from "../common/FieldHint";
import {
  API_KEY,
  API_KEY_FILTER_STATUS_LIST,
  formatApiKeyDisplayStatusLabel,
  formatApiKeyFilterStatusLabel,
  getApiKeyDisplayStatusColorScheme,
} from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";

export interface ApiKeyManagementTabProps {
  /** When true, tab is visible; used to fetch data when user switches to this tab */
  isActive?: boolean;
  /** Parent can trigger refresh after keys are created on another tab */
  onRegisterRefresh?: (refresh: () => Promise<void>) => void;
}

export default function ApiKeyManagementTab({
  isActive = false,
  onRegisterRefresh,
}: ApiKeyManagementTabProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { user } = useAuth();

  const mgmt = useApiKeyManagementTab({
    user: user ?? null,
  });

  const budgetEdit = useApiKeyBudgetEdit({
    tenantId: user?.tenant_id,
    applications: mgmt.applications,
    initialApplicationId:
      mgmt.filterApplication !== "all" ? mgmt.filterApplication : undefined,
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

  const apiKeyColumns = useMemo((): DataTableColumn<ApiKeyTableRow>[] => {
    return [
      {
        id: "key_name",
        header: "Key Name",
        sortable: true,
        sortAccessor: (key) => key.key_name ?? "",
        cell: (key) => (
          <Box>
            <Text fontWeight="medium" fontSize="sm">{key.key_name}</Text>
            {key.api_key && (
              <Text fontSize="xs" color="ink.500" fontFamily="mono">
                {key.api_key}
              </Text>
            )}
          </Box>
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
        cell: (key) => {
          const visiblePerms = mgmt.visiblePermissionsForKey(key);
          return (
            <HStack flexWrap="wrap" spacing={1}>
              {visiblePerms.slice(0, 3).map((perm) => (
                <Badge key={String(perm)} colorScheme="blue" fontSize="xs">
                  {mgmt.formatPermission(perm)}
                </Badge>
              ))}
              {visiblePerms.length > 3 && (
                <Badge colorScheme="gray" fontSize="xs">
                  +{visiblePerms.length - 3}
                </Badge>
              )}
            </HStack>
          );
        },
      },
      {
        id: "budget",
        header: "Budget",
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
              <Text fontSize="sm" fontWeight="semibold" color="blue.600">
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
          const badgeTooltip =
            mgmt.getKeyInactiveReason(key) ?? mgmt.getKeyRevokedReason(key);
          const badge = (
            <Badge colorScheme={getApiKeyDisplayStatusColorScheme(displayStatus)}>
              {formatApiKeyDisplayStatusLabel(displayStatus)}
            </Badge>
          );
          return badgeTooltip ? (
            <Tooltip label={badgeTooltip} placement="top" hasArrow openDelay={300}>
              {badge}
            </Tooltip>
          ) : (
            badge
          );
        },
      },
      {
        id: "created",
        header: "Created",
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
        header: "Expires",
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
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (key) => (
          <DataTableActions
            actions={[
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
  }, [mgmt]);

  useEffect(() => {
    onRegisterRefresh?.(mgmt.handleFetchAllApiKeys);
  }, [onRegisterRefresh, mgmt.handleFetchAllApiKeys]);

  useEffect(() => {
    if (isActive) {
      void mgmt.handleFetchAllApiKeys({ silent: true });
    }
  }, [isActive, mgmt.handleFetchAllApiKeys]);

  return (
    <>
      <DataTable
            layout="admin"
            items={sortedApiKeys}
            columns={apiKeyColumns}
            getRowKey={(key) =>
              key.api_key ?? `id-${key.id ?? ""}-${key.application_id ?? ""}-${key.key_name}`
            }
            onRowClick={mgmt.handleOpenViewModal}
            isLoading={mgmt.isLoadingAllApiKeys}
            loadingMessage="Loading API keys..."
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
            filterToolbarRightContent={
              <>
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="blue"
                  onClick={() => budgetEdit.open()}
                  isDisabled={mgmt.applications.length === 0}
                >
                  Edit Budget
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="blue"
                  onClick={() => void mgmt.handleFetchAllApiKeys()}
                  isLoading={mgmt.isLoadingAllApiKeys}
                  loadingText="Loading..."
                >
                  Refresh
                </Button>
              </>
            }
            search={{
              label: "Key Name",
              value: mgmt.keyNameSearch,
              onChange: mgmt.setKeyNameSearch,
              placeholder: FIELD_HINTS.apiKey.search.placeholder,
              fields: ["key_name"],
            }}
            filterDefs={[
              {
                id: "application",
                label: "Application",
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

      {/* View API Key Modal */}
      <StandardModal
        isOpen={mgmt.isViewModalOpen}
        onClose={mgmt.handleCloseViewModal}
        size="2xl"
        scrollBehavior="inside"
        title="API Key Details"
        description="View this key's application, budget, and permissions."
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          <FormActions
            cancelLabel="Close"
            onCancel={mgmt.handleCloseViewModal}
            hideSubmit
            justify="flex-end"
            pt={0}
          />
        }
      >
            {mgmt.selectedKeyForView && (
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <ReadOnlyField label="Key Name">
                  {mgmt.selectedKeyForView.key_name}
                </ReadOnlyField>
                <ReadOnlyField label="Key ID">
                  <Text fontSize="sm" fontFamily="mono" color="ink.700" wordBreak="break-all">
                    {mgmt.formatKeyId(mgmt.selectedKeyForView)}
                  </Text>
                </ReadOnlyField>
                <ReadOnlyField label="Application">
                  {mgmt.selectedKeyForView.application_name ??
                    mgmt.selectedKeyForView.application_id ??
                    "—"}
                </ReadOnlyField>
                <ReadOnlyField label="Budget">
                  <Text fontSize="sm" color="ink.800">
                    {mgmt.formatBudgetPct(mgmt.selectedKeyForView)}
                  </Text>
                  {mgmt.selectedKeyForView.allocated_budget != null &&
                    mgmt.formatBudgetPct(mgmt.selectedKeyForView) !== "—" && (
                      <Text fontSize="sm" color="ink.500">
                        {formatSpendMoney(mgmt.selectedKeyForView.allocated_budget, "INR")}
                      </Text>
                    )}
                </ReadOnlyField>
                <ReadOnlyField label="Permissions" fullWidth>
                  {(() => {
                    const visiblePerms = mgmt.visiblePermissionsForKey(
                      mgmt.selectedKeyForView,
                    );
                    return visiblePerms.length > 0 ? (
                      <HStack flexWrap="wrap" spacing={2}>
                        {visiblePerms.map((perm) => (
                          <Badge key={String(perm)} colorScheme="blue" fontSize="sm" p={2}>
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
                <ReadOnlyField label="Status">
                  <Badge
                    colorScheme={getApiKeyDisplayStatusColorScheme(
                      mgmt.resolveKeyDisplayStatus(mgmt.selectedKeyForView)
                    )}
                    fontSize="sm"
                    p={2}
                  >
                    {formatApiKeyDisplayStatusLabel(
                      mgmt.resolveKeyDisplayStatus(mgmt.selectedKeyForView)
                    )}
                  </Badge>
                  {(mgmt.getKeyInactiveReason(mgmt.selectedKeyForView) ??
                    mgmt.getKeyRevokedReason(mgmt.selectedKeyForView)) && (
                    <Text fontSize="xs" color="ink.500" mt={2}>
                      {mgmt.getKeyInactiveReason(mgmt.selectedKeyForView) ??
                        mgmt.getKeyRevokedReason(mgmt.selectedKeyForView)}
                    </Text>
                  )}
                </ReadOnlyField>
                <ReadOnlyField label="Created At">
                  {mgmt.selectedKeyForView.created_at
                    ? new Date(mgmt.selectedKeyForView.created_at).toLocaleString()
                    : "—"}
                </ReadOnlyField>
                {mgmt.selectedKeyForView.expires_at ? (
                  <ReadOnlyField label="Expires At">
                    {new Date(mgmt.selectedKeyForView.expires_at).toLocaleString()}
                  </ReadOnlyField>
                ) : null}
                {mgmt.selectedKeyForView.last_used ? (
                  <ReadOnlyField label="Last Used">
                    {new Date(mgmt.selectedKeyForView.last_used).toLocaleString()}
                  </ReadOnlyField>
                ) : null}
              </SimpleGrid>
            )}
      </StandardModal>

      {/* Update API Key Modal */}
      <StandardModal
        isOpen={mgmt.isUpdateModalOpen}
        onClose={mgmt.handleCloseUpdateModal}
        size="lg"
        scrollBehavior="inside"
        title="Update API Key"
        description="Change this key's name and permissions."
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          <FormActions
            submitLabel="Update"
            onCancel={mgmt.handleCloseUpdateModal}
            onSubmit={mgmt.handleUpdateApiKey}
            isLoading={mgmt.isUpdating}
            isDisabled={
              !(mgmt.updateFormData.key_name ?? "").trim() ||
              !(mgmt.updateFormData.permissions?.length ?? 0)
            }
            loadingText="Updating..."
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
      </StandardModal>

      <ConfirmDialog
        isOpen={mgmt.isRevokeModalOpen}
        onClose={mgmt.handleCloseRevokeModal}
        onConfirm={mgmt.handleRevokeApiKey}
        title="Revoke API Key"
        body={
          <VStack align="stretch" spacing={3}>
            <Text>
              Are you sure you want to revoke the API key &quot;{mgmt.keyToRevoke?.key_name}
              &quot;?
            </Text>
            <Box>
              <Text fontWeight="semibold" fontSize="sm" color="ink.700" mb={2}>
                Key Details:
              </Text>
              <VStack align="start" spacing={1} fontSize="sm">
                <Text>
                  <strong>Key:</strong>{" "}
                  {mgmt.keyToRevoke?.api_key
                    ? `${mgmt.keyToRevoke.api_key.slice(0, 8)}…${mgmt.keyToRevoke.api_key.slice(-4)}`
                    : mgmt.keyToRevoke?.id != null
                      ? String(mgmt.keyToRevoke.id)
                      : "—"}
                </Text>
                <Text>
                  <strong>Created:</strong>{" "}
                  {mgmt.keyToRevoke?.created_at
                    ? new Date(mgmt.keyToRevoke.created_at).toLocaleString()
                    : "N/A"}
                </Text>
              </VStack>
            </Box>
            {mgmt.keyToRevoke && (mgmt.keyToRevoke.permissions ?? []).length > 0 && (
              <Box>
                <Text fontWeight="semibold" fontSize="sm" color="ink.700" mb={2}>
                  Permissions (will be revoked):
                </Text>
                <HStack flexWrap="wrap" spacing={2}>
                  {(mgmt.keyToRevoke.permissions ?? []).map((perm) => (
                    <Badge key={String(perm)} colorScheme="orange" fontSize="xs">
                      {mgmt.formatPermission(perm)}
                    </Badge>
                  ))}
                </HStack>
              </Box>
            )}
            <Alert status="warning" borderRadius="md" mt={2}>
              <AlertIcon />
              <AlertDescription fontSize="sm">
                This action will revoke the API key. Revoked keys cannot be reactivated.
              </AlertDescription>
            </Alert>
          </VStack>
        }
        confirmLabel="Revoke"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={mgmt.isRevoking}
        confirmLoadingText="Revoking..."
        leastDestructiveRef={cancelRef}
      />

      <ApiKeyBulkBudgetModal
        isOpen={budgetEdit.isOpen}
        onClose={budgetEdit.close}
        isLoading={budgetEdit.isLoading}
        isSaving={budgetEdit.isSaving}
        banner={budgetEdit.banner}
        applications={budgetEdit.applications}
        selectedApplicationId={budgetEdit.selectedApplicationId}
        onApplicationChange={budgetEdit.onApplicationChange}
        applicationName={budgetEdit.applicationName}
        applicationBudget={budgetEdit.applicationBudget}
        applicationAllocatedPct={budgetEdit.applicationAllocatedPct}
        applicationBudgetUnset={budgetEdit.applicationBudgetUnset}
        liveTotalPct={budgetEdit.liveTotalPct}
        rows={budgetEdit.rows}
        onPctChange={budgetEdit.onPctChange}
        onPctBoundHit={budgetEdit.onPctBoundHit}
        onAmountChange={budgetEdit.onAmountChange}
        onSave={() => void budgetEdit.save()}
        canSave={budgetEdit.canSave}
      />
    </>
  );
}
