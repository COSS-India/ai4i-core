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
  Button,
  ButtonGroup,
  IconButton,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useApiKeyManagementTab, type ApiKeyTableRow } from "./hooks/useApiKeyManagementTab";
import { useApiKeyBudgetEdit } from "./hooks/useApiKeyBudgetEdit";
import { BUDGET_COPY, editBudgetForKey } from "../../config/budgetMessages";
import ApiKeyBulkBudgetModal from "./ApiKeyBulkBudgetModal";
import ApiKeyBudgetModal from "./ApiKeyBudgetModal";
import { RevokeBudgetBreakdown } from "./budgetVisuals";
import { formatSpendMoney } from "../../utils/usageSpendHelpers";
import {
  FiCalendar,
  FiCheck,
  FiClock,
  FiCornerDownRight,
  FiRefreshCw,
  FiSlash,
  FiSliders,
} from "react-icons/fi";
import {
  formatExtension,
  formatTimeUntil,
  GRACE_EXTENSION_OPTIONS,
} from "../../utils/apiKeyUtils";
import { ChevronDownIcon, ChevronRightIcon, CopyIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import StandardModal from "../common/StandardModal";
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
  type ApiKeyDisplayStatusValue,
  formatApiKeyDisplayStatusLabel,
  formatApiKeyFilterStatusLabel,
} from "../../config/constants";
import { FIELD_HINTS } from "../../config/fieldHints";

/** "24 Oct 2026, 6:00 PM IST" in the viewer's own time zone. */
function formatGraceTime(value: string | Date): string {
  // dateStyle/timeStyle can't be combined with timeZoneName (TypeError).
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

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

/**
 * Shows the rotation actions: rotate, extend the previous key, and revoke
 * the current or previous key value on its own. Set to false to hide them.
 */
const SHOW_API_KEY_ROTATION_ACTIONS = true;

export default function ApiKeyManagementTab({
  isActive = false,
  onRegisterRefresh,
  onCreate,
  onBindPageActions,
}: ApiKeyManagementTabProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const rotateCancelRef = useRef<HTMLButtonElement>(null);
  const stopPreviousCancelRef = useRef<HTMLButtonElement>(null);
  const revokeCurrentCancelRef = useRef<HTMLButtonElement>(null);
  const { copy } = useCopyToClipboard();
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

  /** Rotating keys show Current/Previous key sub-rows; ids here are collapsed. */
  const [collapsedKeyIds, setCollapsedKeyIds] = useState<ReadonlySet<number>>(new Set());
  const toggleKeyExpanded = (keyId: number) =>
    setCollapsedKeyIds((prev) => {
      const next = new Set(prev);
      if (next.has(keyId)) next.delete(keyId);
      else next.add(keyId);
      return next;
    });
  const rotationSubRows = (key: ApiKeyTableRow): ApiKeyTableRow[] =>
    !SHOW_API_KEY_ROTATION_ACTIONS ||
    key.subRow ||
    !mgmt.isRotationInProgress(key) ||
    collapsedKeyIds.has(key.id)
      ? []
      : [
          { ...key, subRow: "current" },
          { ...key, subRow: "previous" },
        ];

  const apiKeyColumns = useMemo((): DataTableColumn<ApiKeyTableRow>[] => {
    const formatDate = (value?: string) => (value ? new Date(value).toLocaleDateString() : "—");
    const statusCell = (status: ApiKeyDisplayStatusValue, reason: string | null) => {
      const indicator = (
        <StatusDot label={formatApiKeyDisplayStatusLabel(status)} tone={apiKeyStatusTone(status)} />
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
    };
    const revokeStyle = { color: "red.500", hoverColor: "red.600", hoverBg: "red.50" };

    return [
      {
        id: "key_name",
        header: "Key",
        sortable: true,
        sortAccessor: (key) => key.key_name ?? "",
        cell: (key) => {
          if (key.subRow) {
            return (
              <HStack spacing={2} pl={6}>
                <Box as={FiCornerDownRight} color="ink.400" flexShrink={0} />
                <EntityIdentity
                  name={key.subRow === "current" ? "Current key" : "Previous key"}
                  meta={key.subRow === "current" ? key.api_key : key.rotated_key}
                />
              </HStack>
            );
          }
          const rotating = SHOW_API_KEY_ROTATION_ACTIONS && mgmt.isRotationInProgress(key);
          const collapsed = collapsedKeyIds.has(key.id);
          return (
            <HStack spacing={1}>
              {rotating ? (
                <IconButton
                  aria-label={collapsed ? "Show current and previous key" : "Hide current and previous key"}
                  icon={collapsed ? <ChevronRightIcon /> : <ChevronDownIcon />}
                  size="xs"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleKeyExpanded(key.id);
                  }}
                />
              ) : (
                <Box w={6} flexShrink={0} />
              )}
              <EntityIdentity
                name={key.key_name || "API key"}
                meta={rotating ? undefined : key.api_key}
              />
            </HStack>
          );
        },
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
          if (key.subRow) {
            return <Text fontSize="sm" color="ink.600">Shared</Text>;
          }
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
          if (key.subRow === "current" && key.api_key_revoked_at) {
            return statusCell(
              API_KEY.DISPLAY_STATUS.REVOKED,
              `Revoked ${new Date(key.api_key_revoked_at).toLocaleString()}`,
            );
          }
          return statusCell(
            mgmt.resolveKeyDisplayStatus(key),
            mgmt.getKeyInactiveReason(key) ?? mgmt.getKeyRevokedReason(key),
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
        cell: (key) => {
          if (key.subRow === "current") {
            // The current value was issued by the last rotation.
            return <Text fontSize="sm">{formatDate(key.rotated_at ?? key.created_at)}</Text>;
          }
          return (
            <Box>
              <Text fontSize="sm">{formatDate(key.created_at)}</Text>
              {!key.subRow && key.rotated_at ? (
                <Text fontSize="xs" color="ink.500">
                  Rotated {formatDate(key.rotated_at)}
                </Text>
              ) : null}
            </Box>
          );
        },
      },
      {
        id: "expires",
        header: "Expiry",
        sortable: true,
        sortAccessor: (key) =>
          key.expires_at
            ? new Date(key.expires_at).getTime()
            : Number.POSITIVE_INFINITY,
        cell: (key) => {
          if (key.subRow === "previous") {
            return (
              <Box>
                <Text fontSize="sm">
                  {key.rotated_key_expires_at
                    ? new Date(key.rotated_key_expires_at).toLocaleString()
                    : "—"}
                </Text>
                <Text fontSize="xs" color="ink.500">
                  Grace period ends
                </Text>
              </Box>
            );
          }
          return (
            <Text fontSize="sm">
              {key.expires_at ? new Date(key.expires_at).toLocaleDateString() : "Never"}
            </Text>
          );
        },
      },
      {
        id: "actions",
        header: "Actions",
        align: "right",
        width: SHOW_API_KEY_ROTATION_ACTIONS ? "212px" : "176px",
        minWidth: SHOW_API_KEY_ROTATION_ACTIONS ? "212px" : "176px",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (key) => {
          if (key.subRow === "current") {
            return (
              <DataTableActions
                justify="flex-end"
                actions={[
                  {
                    id: "revoke-current",
                    label: "Revoke current key",
                    tooltip: mgmt.isCurrentKeyLive(key)
                      ? "Revoke the current key now; the previous key keeps working until its grace period ends"
                      : "The current key is already revoked.",
                    icon: <FiSlash />,
                    ...revokeStyle,
                    disabled: !mgmt.isCurrentKeyLive(key),
                    onClick: () => mgmt.handleOpenRevokeCurrentModal(key),
                  },
                ]}
              />
            );
          }
          if (key.subRow === "previous") {
            return (
              <DataTableActions
                justify="flex-end"
                actions={[
                  {
                    id: "extend-previous",
                    label: "Extend grace period",
                    tooltip: "Extend grace period",
                    icon: <FiClock />,
                    onClick: () => mgmt.handleOpenExtendModal(key),
                  },
                  {
                    id: "stop-previous",
                    label: "Revoke previous key",
                    tooltip: mgmt.isCurrentKeyLive(key)
                      ? "Revoke the previous key now; the current key keeps working"
                      : "Revoke the previous key now; the current key is already revoked, so the API key is revoked",
                    icon: <FiSlash />,
                    ...revokeStyle,
                    onClick: () => mgmt.handleOpenStopPreviousModal(key),
                  },
                ]}
              />
            );
          }
          const rotating = SHOW_API_KEY_ROTATION_ACTIONS && mgmt.isRotationInProgress(key);
          return (
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
                ...(SHOW_API_KEY_ROTATION_ACTIONS
                  ? [
                      {
                        id: "rotate",
                        label: "Rotate API key",
                        tooltip: mgmt.isKeyRotatable(key)
                          ? "Rotate key"
                          : rotating && key.rotated_key_expires_at
                            ? `The previous key works until ${new Date(key.rotated_key_expires_at).toLocaleString()}; rotate again after that, or revoke it.`
                            : "Only effectively active API keys can be rotated.",
                        icon: <FiRefreshCw />,
                        disabled: !mgmt.isKeyRotatable(key),
                        onClick: () => mgmt.handleOpenRotateModal(key),
                      },
                    ]
                  : []),
                // While rotating, each key is revoked from its own row.
                ...(rotating
                  ? []
                  : [
                      {
                        id: "revoke",
                        label: "Revoke API key",
                        tooltip: mgmt.isKeyRevocable(key) ? "Revoke key" : "Already revoked",
                        icon: <FiSlash />,
                        ...revokeStyle,
                        disabled: !mgmt.isKeyRevocable(key),
                        onClick: () => mgmt.handleOpenRevokeModal(key),
                      },
                    ]),
              ]}
            />
          );
        },
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toggleKeyExpanded only closes over the setter
  }, [mgmt, openSingleKeyBudget, collapsedKeyIds]);

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
        <ReadOnlyField label={viewKey.rotated_key || viewKey.api_key_revoked_at ? "Current Key" : "Key ID"}>
          <Text fontSize="sm" fontFamily="mono" color="ink.700" wordBreak="break-all">
            {mgmt.formatKeyId(viewKey)}
          </Text>
          {viewKey.api_key_revoked_at ? (
            <Text fontSize="xs" color="red.600" mt={1}>
              Revoked {new Date(viewKey.api_key_revoked_at).toLocaleString()}
            </Text>
          ) : null}
        </ReadOnlyField>
        {mgmt.isRotationInProgress(viewKey) && viewKey.rotated_key ? (
          <ReadOnlyField label="Previous Key">
            <Text fontSize="sm" fontFamily="mono" color="ink.700" wordBreak="break-all">
              {viewKey.rotated_key}
            </Text>
            {viewKey.rotated_key_expires_at ? (
              <Text fontSize="xs" color="ink.500" mt={1}>
                Works until {new Date(viewKey.rotated_key_expires_at).toLocaleString()}
              </Text>
            ) : null}
          </ReadOnlyField>
        ) : null}
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
              `${key.api_key ?? `id-${key.id ?? ""}-${key.application_id ?? ""}-${key.key_name}`}${key.subRow ? `:${key.subRow}` : ""}`
            }
            getSubRows={rotationSubRows}
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

      <ConfirmDialog
        isOpen={Boolean(mgmt.keyToRotate)}
        onClose={mgmt.handleCloseRotateModal}
        onConfirm={mgmt.handleRotateApiKey}
        title={
          mgmt.keyToRotate?.key_name
            ? `Rotate ${mgmt.keyToRotate.key_name}`
            : "Rotate API Key"
        }
        body={
          <VStack align="stretch" spacing={3}>
            <Text fontSize="sm" color="ink.700" lineHeight="1.5">
              A new key is issued for <Text as="b">{mgmt.keyToRotate?.key_name}</Text> and shown
              once. The current key keeps working for the grace period so you can switch your
              applications over, then stops. Budget, permissions and expiry stay the same.
            </Text>
            <FormControl isRequired isInvalid={!mgmt.isRotateGraceDaysValid && mgmt.rotateGraceDays !== ""}>
              <FieldLabel>Grace period (days)</FieldLabel>
              <Input
                type="number"
                min={0}
                step={1}
                value={mgmt.rotateGraceDays}
                onChange={(e) => mgmt.setRotateGraceDays(e.target.value)}
                placeholder="Days"
                isDisabled={mgmt.isRotating}
              />
              <FieldHint>
                {mgmt.defaultGraceDays == null ? "" : `Default ${mgmt.defaultGraceDays} days. `}
                Whole days, 0 or more. Never past the key&apos;s own expiry; you can extend it later.
              </FieldHint>
            </FormControl>
          </VStack>
        }
        confirmLabel="Rotate API Key"
        cancelLabel="Cancel"
        isConfirmDisabled={!mgmt.isRotateGraceDaysValid}
        isConfirmLoading={mgmt.isRotating}
        confirmLoadingText="Rotating..."
        leastDestructiveRef={rotateCancelRef}
      />

      <ConfirmDialog
        isOpen={Boolean(mgmt.keyToStopPrevious)}
        onClose={mgmt.handleCloseStopPreviousModal}
        onConfirm={mgmt.handleStopPreviousKeyValue}
        title={
          mgmt.keyToStopPrevious?.key_name
            ? `Revoke previous value of ${mgmt.keyToStopPrevious.key_name}`
            : "Revoke previous key value"
        }
        body={
          <Text fontSize="sm" color="ink.700" lineHeight="1.5">
            The value <Text as="b">{mgmt.keyToStopPrevious?.key_name}</Text> had before its last
            rotation stops working immediately, instead of on{" "}
            {mgmt.keyToStopPrevious?.rotated_key_expires_at
              ? new Date(mgmt.keyToStopPrevious.rotated_key_expires_at).toLocaleString()
              : "its scheduled date"}
            .{" "}
            {mgmt.keyToStopPrevious && !mgmt.isCurrentKeyLive(mgmt.keyToStopPrevious)
              ? "The current key is already revoked, so the API key is revoked."
              : "The current key keeps working."}
          </Text>
        }
        confirmLabel="Revoke Previous Value"
        cancelLabel="Cancel"
        isConfirmLoading={mgmt.isStoppingPrevious}
        confirmLoadingText="Revoking..."
        leastDestructiveRef={stopPreviousCancelRef}
      />

      <StandardModal
        isOpen={Boolean(mgmt.keyToExtend)}
        onClose={mgmt.handleCloseExtendModal}
        title="Extend grace period"
        description={
          mgmt.keyToExtend
            ? `${mgmt.keyToExtend.key_name} • previous key${mgmt.keyToExtend.rotated_key ? ` (${mgmt.keyToExtend.rotated_key})` : ""}`
            : undefined
        }
        lockDismiss={mgmt.isExtending}
        footer={
          <HStack spacing={3}>
            <Button variant="ghost" onClick={mgmt.handleCloseExtendModal} isDisabled={mgmt.isExtending}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={() => void mgmt.handleExtendPreviousKeyValue()}
              isLoading={mgmt.isExtending}
              loadingText="Extending..."
              isDisabled={Boolean(mgmt.extendError)}
            >
              Extend grace period
            </Button>
          </HStack>
        }
      >
        {mgmt.keyToExtend?.rotated_key_expires_at ? (
          <VStack align="stretch" spacing={4}>
            <Alert status="warning" borderRadius="md" alignItems="flex-start">
              <Box as={FiCalendar} mt={0.5} mr={3} flexShrink={0} />
              <AlertDescription fontSize="sm">
                Current grace period ends on {formatGraceTime(mgmt.keyToExtend.rotated_key_expires_at)}{" "}
                (in {formatTimeUntil(mgmt.keyToExtend.rotated_key_expires_at)})
              </AlertDescription>
            </Alert>
            <FormControl>
              <FieldLabel>Select extension duration</FieldLabel>
              <ButtonGroup size="sm" isAttached w="100%" role="radiogroup" aria-label="Extension duration">
                {[...GRACE_EXTENSION_OPTIONS, { id: "custom" as const, label: "Custom..." }].map((option) => {
                  const selected = mgmt.extendOption === option.id;
                  return (
                    <Button
                      key={option.id}
                      flex={1}
                      role="radio"
                      aria-checked={selected}
                      leftIcon={selected ? <FiCheck /> : undefined}
                      variant="outline"
                      colorScheme={selected ? "blue" : "gray"}
                      bg={selected ? "blue.50" : undefined}
                      onClick={() => mgmt.setExtendOption(option.id)}
                      isDisabled={mgmt.isExtending}
                    >
                      {option.label}
                    </Button>
                  );
                })}
              </ButtonGroup>
            </FormControl>
            {mgmt.extendOption === "custom" ? (
              <FormControl isRequired>
                <FieldLabel>Works until</FieldLabel>
                <Input
                  type="datetime-local"
                  value={mgmt.extendCustomUntil}
                  onChange={(e) => mgmt.setExtendCustomUntil(e.target.value)}
                  isDisabled={mgmt.isExtending}
                />
              </FormControl>
            ) : null}
            {mgmt.extendNewEnd && !mgmt.extendError ? (
              <Alert status="info" borderRadius="md">
                <AlertDescription fontSize="sm">
                  New grace period will end on {formatGraceTime(mgmt.extendNewEnd)} (extended by{" "}
                  {formatExtension(mgmt.keyToExtend.rotated_key_expires_at, mgmt.extendNewEnd)})
                </AlertDescription>
              </Alert>
            ) : mgmt.extendError && (mgmt.extendOption !== "custom" || mgmt.extendCustomUntil) ? (
              <Alert status="error" borderRadius="md">
                <AlertDescription fontSize="sm">{mgmt.extendError}</AlertDescription>
              </Alert>
            ) : null}
            <Text fontSize="xs" color="ink.500">
              This extends only the previous key. The current key is not affected.
            </Text>
          </VStack>
        ) : null}
      </StandardModal>

      <ConfirmDialog
        isOpen={Boolean(mgmt.keyToRevokeCurrent)}
        onClose={mgmt.handleCloseRevokeCurrentModal}
        onConfirm={mgmt.handleRevokeCurrentKeyValue}
        title={
          mgmt.keyToRevokeCurrent?.key_name
            ? `Revoke current key of ${mgmt.keyToRevokeCurrent.key_name}`
            : "Revoke current key"
        }
        body={
          <Text fontSize="sm" color="ink.700" lineHeight="1.5">
            The current key of <Text as="b">{mgmt.keyToRevokeCurrent?.key_name}</Text> stops
            working immediately. The previous key keeps working until{" "}
            {mgmt.keyToRevokeCurrent?.rotated_key_expires_at
              ? new Date(mgmt.keyToRevokeCurrent.rotated_key_expires_at).toLocaleString()
              : "its window ends"}
            ; after that the API key stops working entirely and a new key must be created.
          </Text>
        }
        confirmLabel="Revoke Current Key"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={mgmt.isRevokingCurrent}
        confirmLoadingText="Revoking..."
        leastDestructiveRef={revokeCurrentCancelRef}
      />

      <StandardModal
        isOpen={Boolean(mgmt.rotatedKey)}
        onClose={mgmt.handleCloseRotatedKey}
        title="API Key Rotated"
        lockDismiss
        footer={
          <Button colorScheme="blue" onClick={mgmt.handleCloseRotatedKey}>
            I&apos;ve saved the new key
          </Button>
        }
      >
        {mgmt.rotatedKey ? (
          <VStack align="stretch" spacing={4}>
            <Alert status="warning" borderRadius="md" variant="left-accent">
              <AlertIcon />
              <AlertDescription fontSize="sm">
                Copy the new key now. It will not be shown again.
              </AlertDescription>
            </Alert>
            <HStack align="stretch" spacing={2}>
              <Input
                value={mgmt.rotatedKey.api_key}
                isReadOnly
                fontFamily="mono"
                fontSize="xs"
                aria-label="New API key"
              />
              <Button
                size="sm"
                flexShrink={0}
                leftIcon={<CopyIcon />}
                onClick={() => {
                  void copy(mgmt.rotatedKey!.api_key, "API key copied to clipboard");
                }}
              >
                Copy
              </Button>
            </HStack>
            <Text fontSize="sm" color="ink.700">
              The previous key for <Text as="b">{mgmt.rotatedKey.key_name}</Text> keeps working
              until{" "}
              <Text as="b">{new Date(mgmt.rotatedKey.rotated_key_expires_at).toLocaleString()}</Text>
              . Revoking the key stops both immediately.
            </Text>
          </VStack>
        ) : null}
      </StandardModal>

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
