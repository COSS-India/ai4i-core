import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  HStack,
  Heading,
  IconButton,
  Text,
  Tooltip,
} from "@chakra-ui/react";
import { EditIcon, ViewIcon } from "@chakra-ui/icons";
import React, { useMemo, useState } from "react";
import { FiSlash } from "react-icons/fi";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../../common/AdminDataTable";
import {
  API_KEY,
  API_KEY_FILTER_STATUS_LIST,
  formatApiKeyDisplayStatusLabel,
  formatApiKeyFilterStatusLabel,
  getApiKeyDisplayStatusColorScheme,
  type ApiKeyDisplayStatusValue,
} from "../../../config/constants";
import type { AdminAPIKeyWithUserResponse } from "../../../types/auth";

export interface ApiKeyManagementTableProps {
  apiKeys: AdminAPIKeyWithUserResponse[];
  unfilteredCount: number;
  isLoading: boolean;
  keyNameSearch: string;
  onKeyNameSearchChange: (value: string) => void;
  filterPermission: string;
  onFilterPermissionChange: (value: string) => void;
  filterActive: string;
  onFilterActiveChange: (value: string) => void;
  permissionFilterOptions: string[];
  onClearFilters: () => void;
  onRefresh: () => void;
  onView: (key: AdminAPIKeyWithUserResponse) => void;
  onUpdate: (key: AdminAPIKeyWithUserResponse) => void;
  onRevoke: (key: AdminAPIKeyWithUserResponse) => void;
  formatPermission: (permissionId: number | string) => string;
  resolveKeyDisplayStatus: (key: AdminAPIKeyWithUserResponse) => ApiKeyDisplayStatusValue;
  getKeyInactiveReason: (key: AdminAPIKeyWithUserResponse) => string | null;
  isKeyEffectivelyActive: (key: AdminAPIKeyWithUserResponse) => boolean;
  isKeyRevocable: (key: AdminAPIKeyWithUserResponse) => boolean;
  cardBg: string;
  cardBorder: string;
}

const ApiKeyManagementTable: React.FC<ApiKeyManagementTableProps> = ({
  apiKeys,
  unfilteredCount,
  isLoading,
  keyNameSearch,
  onKeyNameSearchChange,
  filterPermission,
  onFilterPermissionChange,
  filterActive,
  onFilterActiveChange,
  permissionFilterOptions,
  onClearFilters,
  onRefresh,
  onView,
  onUpdate,
  onRevoke,
  formatPermission,
  resolveKeyDisplayStatus,
  getKeyInactiveReason,
  isKeyEffectivelyActive,
  isKeyRevocable,
  cardBg,
  cardBorder,
}) => {
  const [keyNameSortDirection, setKeyNameSortDirection] = useState<"asc" | "desc">("asc");

  const sortedApiKeys = useMemo(() => {
    return [...apiKeys].sort((a, b) => {
      const aName = a.key_name ?? "";
      const bName = b.key_name ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return keyNameSortDirection === "asc" ? nameCmp : -nameCmp;

      const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
      const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
      return timeB - timeA;
    });
  }, [apiKeys, keyNameSortDirection]);

  const hasActiveFilters =
    filterPermission !== "all" || filterActive !== "all" || keyNameSearch.trim() !== "";

  const columns = useMemo((): AdminTableColumn<AdminAPIKeyWithUserResponse>[] => {
    return [
      {
        id: "key_name",
        header: "Key Name",
        sortable: {
          label: "Key Name",
          direction: keyNameSortDirection,
          onAsc: () => setKeyNameSortDirection("asc"),
          onDesc: () => setKeyNameSortDirection("desc"),
          ascAriaLabel: "Sort API keys by name ascending",
          descAriaLabel: "Sort API keys by name descending",
        },
        cell: (key) => <Text fontWeight="semibold">{key.key_name}</Text>,
      },
      {
        id: "permissions",
        header: "Permissions",
        cell: (key) => (
          <HStack flexWrap="wrap" spacing={1}>
            {(key.permissions ?? []).slice(0, 3).map((perm) => (
              <Badge key={String(perm)} colorScheme="blue" fontSize="xs">
                {formatPermission(perm)}
              </Badge>
            ))}
            {(key.permissions ?? []).length > 3 && (
              <Badge colorScheme="gray" fontSize="xs">
                +{(key.permissions ?? []).length - 3}
              </Badge>
            )}
          </HStack>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (key) => {
          const displayStatus = resolveKeyDisplayStatus(key);
          const inactiveReason = getKeyInactiveReason(key);
          const badge = (
            <Badge colorScheme={getApiKeyDisplayStatusColorScheme(displayStatus)}>
              {formatApiKeyDisplayStatusLabel(displayStatus)}
            </Badge>
          );
          return inactiveReason ? (
            <Tooltip label={inactiveReason} placement="top" hasArrow openDelay={300}>
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
        cell: (key) => (
          <Text fontSize="sm">
            {key.created_at ? new Date(key.created_at).toLocaleDateString() : "—"}
          </Text>
        ),
      },
      {
        id: "expires",
        header: "Expires",
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
          <HStack spacing={1}>
            <Tooltip label="View details" hasArrow placement="top">
              <IconButton
                aria-label="View API key"
                icon={<ViewIcon />}
                size="sm"
                variant="ghost"
                colorScheme="blue"
                _hover={{ bg: "blue.50" }}
                onClick={(e) => {
                  e.stopPropagation();
                  onView(key);
                }}
              />
            </Tooltip>
            <Tooltip
              hasArrow
              label={
                isKeyEffectivelyActive(key)
                  ? "Update key"
                  : isKeyRevocable(key)
                    ? "Only effectively active API keys can be updated."
                    : "This API key has been revoked and cannot be updated."
              }
            >
              <IconButton
                aria-label="Update API key"
                icon={<EditIcon />}
                size="sm"
                variant="ghost"
                colorScheme="green"
                _hover={{ bg: "green.50" }}
                onClick={(e) => {
                  e.stopPropagation();
                  onUpdate(key);
                }}
                isDisabled={!isKeyEffectivelyActive(key)}
              />
            </Tooltip>
            <Tooltip hasArrow label={isKeyRevocable(key) ? "Revoke key" : "Already revoked"}>
              <IconButton
                aria-label="Revoke API key"
                icon={<FiSlash />}
                size="sm"
                variant="ghost"
                colorScheme="orange"
                _hover={{ bg: "orange.50" }}
                onClick={(e) => {
                  e.stopPropagation();
                  onRevoke(key);
                }}
                isDisabled={!isKeyRevocable(key)}
              />
            </Tooltip>
          </HStack>
        ),
      },
    ];
  }, [
    formatPermission,
    getKeyInactiveReason,
    isKeyEffectivelyActive,
    isKeyRevocable,
    keyNameSortDirection,
    onRevoke,
    onUpdate,
    onView,
    resolveKeyDisplayStatus,
  ]);

  return (
    <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
      <CardHeader>
        <HStack justify="space-between">
          <Heading size="md" color="gray.700" userSelect="none" cursor="default">
            Your API Keys
          </Heading>
          <Button
            size="sm"
            colorScheme="blue"
            onClick={onRefresh}
            isLoading={isLoading}
            loadingText="Loading..."
          >
            Refresh
          </Button>
        </HStack>
      </CardHeader>
      <CardBody>
        <AdminDataTable
          items={sortedApiKeys}
          columns={columns}
          getRowKey={(key) => key.api_key ?? `id-${key.id ?? ""}-${key.user_id}-${key.key_name}`}
          onRowClick={onView}
          isLoading={isLoading}
          loadingMessage="Loading API keys..."
          emptyMessage="No API keys found. Click 'Refresh' to load API keys."
          noResultsMessage="No API keys match the current filters."
          unfilteredCount={unfilteredCount}
          hasActiveFilters={hasActiveFilters}
          onClearFilters={onClearFilters}
          showFiltersHeading
          filtersHeading="Filters"
          filters={
            <>
              <TableSearchField
                label="Key Name"
                value={keyNameSearch}
                onChange={onKeyNameSearchChange}
                placeholder="Search by key name"
              />
              <TableSelectField
                label="Permission"
                value={filterPermission}
                onChange={onFilterPermissionChange}
                formControlProps={{ w: { base: "full", md: "320px" } }}
              >
                <option value="all">All Permissions</option>
                {permissionFilterOptions.map((perm) => (
                  <option key={perm} value={perm}>
                    {perm}
                  </option>
                ))}
              </TableSelectField>
              <TableSelectField
                label="Status"
                value={filterActive}
                onChange={onFilterActiveChange}
                formControlProps={{ w: { base: "full", sm: "160px" } }}
              >
                <option value={API_KEY.FILTER_STATUS.ALL}>All</option>
                {API_KEY_FILTER_STATUS_LIST.map((s) => (
                  <option key={s} value={s}>
                    {formatApiKeyFilterStatusLabel(s)}
                  </option>
                ))}
              </TableSelectField>
            </>
          }
        />
      </CardBody>
    </Card>
  );
};

export default ApiKeyManagementTable;
