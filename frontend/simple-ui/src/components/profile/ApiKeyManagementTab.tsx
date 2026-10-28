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
  isGraceWithinExpiry,
  ROTATION_GRACE_OPTIONS,
} from "../../utils/apiKeyUtils";
import { ChevronDownIcon, ChevronRightIcon, CopyIcon, EditIcon } from "@chakra-ui/icons";
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
  createActionsColumn,
  DEFAULT_PAGE_SIZE_OPTIONS,
  FieldLabel,
  type DataTableAction,
  type DataTableColumn,
} from "../common/table";
import { useDeferredColumnSort } from "../../utils/tableSort";
import ConfirmDialog from "../common/ConfirmDialog";
import ApiKeyRotationDialogs from "./ApiKeyRotationDialogs";
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
  isApiKeyExpired,
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

/**
 * Shows the rotation actions: rotate, extend the previous key, and revoke the
 * previous key. Set to false to hide them.
 */
const SHOW_API_KEY_ROTATION_ACTIONS = true;

/** Tooltip for an action that needs an effectively active key. */
function inactiveKeyTooltip(
  isActive: boolean,
  isRevocable: boolean,
  activeText: string,
  inactiveText: string,
  revokedText: string,
): string {
  if (isActive) return activeText;
  return isRevocable ? inactiveText : revokedText;
}

/** Why a key can or can't be rotated right now. */
function rotateTooltip(key: ApiKeyTableRow, isRotatable: boolean, rotating: boolean): string {
  if (isRotatable) return "Rotate key";
  if (rotating && key.rotated_key_expires_at) {
    return `The old key works until ${new Date(key.rotated_key_expires_at).toLocaleString()}; rotate again after that, or revoke it.`;
  }
  if (isApiKeyExpired(key.expires_at)) return "This API key has expired; create a new API key instead.";
  return "Only effectively active API keys can be rotated.";
}

function formatApiKeyTableDate(value?: string): string {
  return value ? new Date(value).toLocaleDateString() : "—";
}

function formatApiKeyTableDateTime(value?: string): string {
  return value ? new Date(value).toLocaleString() : "—";
}

function ApiKeyStatusCell({
  status,
  reason,
}: Readonly<{
  status: ApiKeyDisplayStatusValue;
  reason: string | null;
}>) {
  const indicator = (
    <StatusDot label={formatApiKeyDisplayStatusLabel(status)} tone={apiKeyStatusTone(status)} />
  );
  if (!reason) return indicator;
  return (
    <Tooltip label={reason} placement="top" hasArrow openDelay={300}>
      <Box as="span" tabIndex={0} display="inline-flex">
        {indicator}
      </Box>
    </Tooltip>
  );
}

function renderApiKeyCreatedCell(key: ApiKeyTableRow): React.ReactNode {
  const value = key.subRow === "current" ? key.rotated_at ?? key.created_at : key.created_at;
  return (
    <Text fontSize="sm" color="ink.600">
      {formatApiKeyTableDate(value)}
    </Text>
  );
}

function renderApiKeyExpiryCell(key: ApiKeyTableRow): React.ReactNode {
  if (key.subRow === "previous") {
    return (
      <VStack align="start" spacing={0}>
        <Text fontSize="sm" color="ink.600">
          {formatApiKeyTableDateTime(key.rotated_key_expires_at)}
        </Text>
        <Text fontSize="xs" color="ink.500">
          Grace period ends
        </Text>
      </VStack>
    );
  }
  return (
    <Text fontSize="sm" color="ink.600">
      {key.expires_at ? formatApiKeyTableDate(key.expires_at) : "Never"}
    </Text>
  );
}

type ApiKeyManagement = ReturnType<typeof useApiKeyManagementTab>;

/** Read-only details of one key, shown in the view drawer. */
function ApiKeyDetails({
  mgmt,
  viewKey,
}: {
  mgmt: ApiKeyManagement;
  viewKey: NonNullable<ApiKeyManagement["selectedKeyForView"]>;
}) {
  return (
    <>
        <FormSection title="API Key">
          <ReadOnlyField label="Key Name">{viewKey.key_name}</ReadOnlyField>
          <ReadOnlyField label={viewKey.rotated_key ? "New Key" : "API Key"}>
            <Text fontSize="sm" fontFamily="mono" color="ink.700" wordBreak="break-all">
              {mgmt.formatKeyId(viewKey)}
            </Text>
          </ReadOnlyField>
          {mgmt.isRotationInProgress(viewKey) && viewKey.rotated_key ? (
            <ReadOnlyField label="Old Key">
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
  );
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
    const subRowActions: Record<"current" | "previous", (key: ApiKeyTableRow) => DataTableAction[]> = {
      current: (key) => [
        {
          // Revoking the rotated key revokes the API key: both keys stop.
          id: "revoke",
          label: "Revoke API key",
          tooltip: "Revoke the API key; the new and old keys both stop",
          icon: <FiSlash />,
          ...revokeStyle,
          onClick: () => mgmt.handleOpenRevokeModal(key),
        },
      ],
      previous: (key) => [
        {
          id: "extend-previous",
          label: "Extend grace period",
          tooltip: "Extend grace period",
          icon: <FiClock />,
          onClick: () => mgmt.handleOpenExtendModal(key),
        },
        {
          id: "stop-previous",
          label: "Revoke old key",
          tooltip: "Revoke the old key now; the new key keeps working",
          icon: <FiSlash />,
          ...revokeStyle,
          onClick: () => mgmt.handleOpenStopPreviousModal(key),
        },
      ],
    };

    const keyActions = (key: ApiKeyTableRow): DataTableAction[] => {
      const rotating = SHOW_API_KEY_ROTATION_ACTIONS && mgmt.isRotationInProgress(key);
      const actions: DataTableAction[] = [
        {
          id: "edit",
          label: "Update API key",
          tooltip: inactiveKeyTooltip(
            mgmt.isKeyEffectivelyActive(key),
            mgmt.isKeyRevocable(key),
            "Update key",
            "Only effectively active API keys can be updated.",
            "This API key has been revoked and cannot be updated.",
          ),
          icon: <EditIcon />,
          disabled: !mgmt.isKeyEffectivelyActive(key),
          onClick: () => mgmt.handleOpenUpdateModal(key),
        },
        {
          id: "budget",
          label: "Edit budget",
          tooltip: key.application_id
            ? inactiveKeyTooltip(
                mgmt.isKeyEffectivelyActive(key),
                mgmt.isKeyRevocable(key),
                BUDGET_COPY.editBudget,
                "Only effectively active API keys can have their budget edited.",
                "This API key has been revoked and cannot have its budget edited.",
              )
            : BUDGET_COPY.keyHasNoApplication,
          "aria-label": editBudgetForKey(key.key_name),
          icon: <FiSliders />,
          disabled: !key.application_id || !mgmt.isKeyEffectivelyActive(key),
          onClick: () => {
            if (key.application_id) {
              openSingleKeyBudget(key.application_id, key.id, key.key_name);
            }
          },
        },
      ];
      if (SHOW_API_KEY_ROTATION_ACTIONS) {
        actions.push({
          id: "rotate",
          label: "Rotate API key",
          tooltip: rotateTooltip(key, mgmt.isKeyRotatable(key), rotating),
          icon: <FiRefreshCw />,
          disabled: !mgmt.isKeyRotatable(key),
          onClick: () => mgmt.handleOpenRotateModal(key),
        });
      }
      // While rotating, each key is revoked from its own row.
      if (!rotating) {
        actions.push({
          id: "revoke",
          label: "Revoke API key",
          tooltip: mgmt.isKeyRevocable(key) ? "Revoke key" : "Already revoked",
          icon: <FiSlash />,
          ...revokeStyle,
          disabled: !mgmt.isKeyRevocable(key),
          onClick: () => mgmt.handleOpenRevokeModal(key),
        });
      }
      return actions;
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
                  name={key.subRow === "current" ? "New Key" : "Old Key"}
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
                  aria-label={collapsed ? "Show new and old key" : "Hide new and old key"}
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
        thProps: { maxW: "200px" },
        tdProps: { maxW: "200px" },
        sortable: true,
        sortAccessor: (key) => key.application_name ?? key.application_id ?? "",
        cell: (key) => (
          <Tooltip
            label={key.application_name ?? key.application_id ?? "—"}
            placement="top"
            hasArrow
            openDelay={300}
          >
            <Text fontSize="sm" isTruncated maxW="180px">
              {key.application_name ?? key.application_id ?? "—"}
            </Text>
          </Tooltip>
        ),
      },
      {
        id: "permissions",
        header: "Permissions",
        hint: FIELD_HINTS.apiKey.col.permissions,
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
        hint: FIELD_HINTS.apiKey.col.allocation,
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
        hint: FIELD_HINTS.apiKey.col.status,
        cell: (key) => (
          <ApiKeyStatusCell
            status={mgmt.resolveKeyDisplayStatus(key)}
            reason={mgmt.getKeyInactiveReason(key) ?? mgmt.getKeyRevokedReason(key)}
          />
        ),
      },
      {
        id: "created",
        header: "Created Date",
        sortable: true,
        sortAccessor: (key) => {
          const value = key.subRow === "current" ? key.rotated_at ?? key.created_at : key.created_at;
          return value ? new Date(value).getTime() : 0;
        },
        cell: renderApiKeyCreatedCell,
      },
      {
        id: "expires",
        header: "Expiry Date",
        hint: FIELD_HINTS.apiKey.col.expiry,
        sortable: true,
        sortAccessor: (key) => {
          const value = key.subRow === "previous" ? key.rotated_key_expires_at : key.expires_at;
          return value ? new Date(value).getTime() : Number.POSITIVE_INFINITY;
        },
        cell: renderApiKeyExpiryCell,
      },
      createActionsColumn<ApiKeyTableRow>({
        // Parent rows: edit + budget (+ rotate/revoke when enabled). Row click opens details.
        actionCount: SHOW_API_KEY_ROTATION_ACTIONS ? 4 : 3,
        getActions: (key) =>
          (key.subRow ? subRowActions[key.subRow] : keyActions)(key),
      }),
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
  const readyRevokeBudget = mgmt.revokeBudget?.status === "ready" ? mgmt.revokeBudget : undefined;

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
        {viewKey ? <ApiKeyDetails mgmt={mgmt} viewKey={viewKey} /> : null}
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
                <FieldLabel hint={FIELD_HINTS.apiKey.keyName.tip}>Key Name</FieldLabel>
                <Input
                  value={mgmt.updateFormData.key_name || ""}
                  onChange={(e) =>
                    mgmt.setUpdateFormData({ ...mgmt.updateFormData, key_name: e.target.value })
                  }
                  bg="white"
                />
              </FormControl>
              <FormControl isRequired>
                <FieldLabel hint={FIELD_HINTS.apiKey.permissions.tip}>Permissions</FieldLabel>
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
              Revoking <Text as="b">{mgmt.keyToRevoke?.key_name}</Text> stops{" "}
              {mgmt.keyToRevoke && mgmt.isRotationInProgress(mgmt.keyToRevoke)
                ? "both its new and old keys"
                : "it from working"}{" "}
              immediately. This can&apos;t be undone.
            </Text>
            <RevokeBudgetBreakdown
              status={mgmt.revokeBudget?.status ?? "loading"}
              allocated={readyRevokeBudget?.allocated}
              consumed={readyRevokeBudget?.consumed}
              unused={readyRevokeBudget?.unused}
              applicationName={readyRevokeBudget?.applicationName}
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

      <ApiKeyRotationDialogs mgmt={mgmt} />

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
