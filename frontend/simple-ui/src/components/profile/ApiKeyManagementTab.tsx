import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Heading,
  Input,
  HStack,
  Text,
  VStack,
  Alert,
  AlertIcon,
  AlertDescription,
  SimpleGrid,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Checkbox,
  CheckboxGroup,
  Tooltip,
  IconButton,
  Badge,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useApiKeyManagementTab } from "./hooks/useApiKeyManagementTab";
import type { AdminAPIKeyWithUserResponse } from "../../types/auth";
import { FiSlash } from "react-icons/fi";
import { ViewIcon, EditIcon } from "@chakra-ui/icons";
import { useAdminTableSurface } from "../common/TableControls";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import StandardModal from "../common/StandardModal";
import { LABELS } from "../../constants";
import {
  API_KEY,
  API_KEY_FILTER_STATUS_LIST,
  formatApiKeyDisplayStatusLabel,
  formatApiKeyFilterStatusLabel,
  getApiKeyDisplayStatusColorScheme,
} from '../../constants';

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
  const { cardBg, borderColor: cardBorder } = useAdminTableSurface();

  const mgmt = useApiKeyManagementTab({
    user: user ?? null,
  });

  const [keyNameSortDirection, setKeyNameSortDirection] = useState<"asc" | "desc">("asc");

  const sortedApiKeys = useMemo(() => {
    return [...mgmt.filteredApiKeys].sort((a, b) => {
      const aName = a.key_name ?? "";
      const bName = b.key_name ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return keyNameSortDirection === "asc" ? nameCmp : -nameCmp;

      const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
      const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
      return timeB - timeA;
    });
  }, [mgmt.filteredApiKeys, keyNameSortDirection]);

  const hasActiveFilters =
    mgmt.filterPermission !== "all" ||
    mgmt.filterActive !== "all" ||
    mgmt.keyNameSearch.trim() !== "";

  const apiKeyColumns = useMemo((): AdminTableColumn<AdminAPIKeyWithUserResponse>[] => {
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
                {mgmt.formatPermission(perm)}
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
          const displayStatus = mgmt.resolveKeyDisplayStatus(key);
          const inactiveReason = mgmt.getKeyInactiveReason(key);
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
                  mgmt.handleOpenViewModal(key);
                }}
              />
            </Tooltip>
            <Tooltip
              hasArrow
              label={
                mgmt.isKeyEffectivelyActive(key)
                  ? "Update key"
                  : mgmt.isKeyRevocable(key)
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
                  mgmt.handleOpenUpdateModal(key);
                }}
                isDisabled={!mgmt.isKeyEffectivelyActive(key)}
              />
            </Tooltip>
            <Tooltip
              hasArrow
              label={mgmt.isKeyRevocable(key) ? "Revoke key" : "Already revoked"}
            >
              <IconButton
                aria-label="Revoke API key"
                icon={<FiSlash />}
                size="sm"
                variant="ghost"
                colorScheme="orange"
                _hover={{ bg: "orange.50" }}
                onClick={(e) => {
                  e.stopPropagation();
                  mgmt.handleOpenRevokeModal(key);
                }}
                isDisabled={!mgmt.isKeyRevocable(key)}
              />
            </Tooltip>
          </HStack>
        ),
      },
    ];
  }, [keyNameSortDirection, mgmt]);

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
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="gray.700" userSelect="none" cursor="default">
              Your API Keys
            </Heading>
            <Button
              size="sm"
              colorScheme="blue"
              onClick={() => void mgmt.handleFetchAllApiKeys()}
              isLoading={mgmt.isLoadingAllApiKeys}
              loadingText={LABELS.STATUS.LOADING}
            >
              Refresh
            </Button>
          </HStack>
        </CardHeader>
        <CardBody>
          <AdminDataTable
            items={sortedApiKeys}
            columns={apiKeyColumns}
            getRowKey={(key) =>
              key.api_key ?? `id-${key.id ?? ""}-${key.user_id}-${key.key_name}`
            }
            onRowClick={mgmt.handleOpenViewModal}
            isLoading={mgmt.isLoadingAllApiKeys}
            loadingMessage="Loading API keys..."
            emptyMessage="No API keys found. Click 'Refresh' to load API keys."
            noResultsMessage="No API keys match the current filters."
            unfilteredCount={mgmt.allApiKeys.length}
            hasActiveFilters={hasActiveFilters}
            onClearFilters={mgmt.handleResetFilters}
            showFiltersHeading
            filtersHeading="Filters"
            filters={
              <>
                <TableSearchField
                  label="Key Name"
                  value={mgmt.keyNameSearch}
                  onChange={mgmt.setKeyNameSearch}
                  placeholder="Search by key name"
                />
                <TableSelectField
                  label="Permission"
                  value={mgmt.filterPermission}
                  onChange={mgmt.setFilterPermission}
                  formControlProps={{ w: { base: "full", md: "320px" } }}
                >
                  <option value="all">All Permissions</option>
                  {mgmt.permissionFilterOptions.map((perm) => (
                    <option key={perm.name} value={perm.name}>
                      {perm.label}
                    </option>
                  ))}
                </TableSelectField>
                <TableSelectField
                  label="Status"
                  value={mgmt.filterActive}
                  onChange={mgmt.setFilterActive}
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

      {/* View API Key Modal */}
      <StandardModal
        isOpen={mgmt.isViewModalOpen}
        onClose={mgmt.handleCloseViewModal}
        size="2xl"
        title="API Key Details"
        footer={<Button onClick={mgmt.handleCloseViewModal}>Close</Button>}
        contentProps={{ maxW: "900px", maxH: "600px" }}
        bodyProps={{ overflowY: "auto" }}
      >
            {mgmt.selectedKeyForView && (
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                    Key Name
                  </Text>
                  <Text fontSize="md">{mgmt.selectedKeyForView.key_name}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                    Key ID
                  </Text>
                  <Text
                    fontSize="sm"
                    fontFamily="mono"
                    color="gray.700"
                    wordBreak="break-all"
                  >
                    {mgmt.formatKeyId(mgmt.selectedKeyForView)}
                  </Text>
                </Box>
                <Box gridColumn={{ base: "span 1", md: "span 2" }}>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>
                    Permissions
                  </Text>
                  {(mgmt.selectedKeyForView.permissions ?? []).length > 0 ? (
                    <HStack flexWrap="wrap" spacing={2}>
                      {(mgmt.selectedKeyForView.permissions ?? []).map((perm) => (
                        <Badge key={String(perm)} colorScheme="blue" fontSize="sm" p={2}>
                          {mgmt.formatPermission(perm)}
                        </Badge>
                      ))}
                    </HStack>
                  ) : (
                    <Text fontSize="sm" color="gray.500">
                      No permissions assigned
                    </Text>
                  )}
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                    Status
                  </Text>
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
                  {mgmt.getKeyInactiveReason(mgmt.selectedKeyForView) && (
                    <Text fontSize="xs" color="gray.500" mt={2}>
                      {mgmt.getKeyInactiveReason(mgmt.selectedKeyForView)}
                    </Text>
                  )}
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                    Created At
                  </Text>
                  <Text fontSize="sm">
                    {mgmt.selectedKeyForView.created_at
                      ? new Date(mgmt.selectedKeyForView.created_at).toLocaleString()
                      : "—"}
                  </Text>
                </Box>
                {mgmt.selectedKeyForView.expires_at && (
                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      Expires At
                    </Text>
                    <Text fontSize="sm">
                      {new Date(mgmt.selectedKeyForView.expires_at).toLocaleString()}
                    </Text>
                  </Box>
                )}
                {mgmt.selectedKeyForView.last_used && (
                  <Box>
                    <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                      Last Used
                    </Text>
                    <Text fontSize="sm">
                      {new Date(mgmt.selectedKeyForView.last_used).toLocaleString()}
                    </Text>
                  </Box>
                )}
              </SimpleGrid>
            )}
      </StandardModal>

      {/* Update API Key Modal */}
      <StandardModal
        isOpen={mgmt.isUpdateModalOpen}
        onClose={mgmt.handleCloseUpdateModal}
        size="lg"
        title="Update API Key"
        footer={
          <>
            <Button
              variant="ghost"
              mr={3}
              onClick={mgmt.handleCloseUpdateModal}
              isDisabled={mgmt.isUpdating}
            >
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={mgmt.handleUpdateApiKey}
              isLoading={mgmt.isUpdating}
              loadingText="Updating..."
              isDisabled={
                mgmt.isUpdating ||
                !(mgmt.updateFormData.key_name ?? "").trim() ||
                !(mgmt.updateFormData.permissions?.length ?? 0)
              }
            >
              Update
            </Button>
          </>
        }
      >
        <VStack spacing={4} align="stretch">
              <FormControl>
                <FormLabel fontWeight="semibold">Key Name</FormLabel>
                <Input
                  value={mgmt.updateFormData.key_name || ""}
                  onChange={(e) =>
                    mgmt.setUpdateFormData({ ...mgmt.updateFormData, key_name: e.target.value })
                  }
                  bg="white"
                />
              </FormControl>
              <FormControl>
                <FormLabel fontWeight="semibold">Permissions</FormLabel>
                <Text fontSize="sm" color="gray.600" mb={3}>
                  Select permissions for this API key
                </Text>
                {mgmt.permissions.length > 0 ? (
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
                        {mgmt.permissions.map((perm) => (
                          <Checkbox key={perm.name} value={perm.name} colorScheme="blue">
                            <Text fontSize="sm">{perm.label}</Text>
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
                <Text fontSize="xs" color="gray.500">
                  Key: {mgmt.selectedKeyForUpdate.api_key.slice(0, 8)}…
                  {mgmt.selectedKeyForUpdate.api_key.slice(-4)}
                </Text>
              )}
        </VStack>
      </StandardModal>

      {/* Revoke API Key Alert Dialog */}
      <AlertDialog
        isOpen={mgmt.isRevokeModalOpen}
        leastDestructiveRef={cancelRef}
        onClose={mgmt.handleCloseRevokeModal}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Revoke API Key
            </AlertDialogHeader>
            <AlertDialogBody>
              <VStack align="stretch" spacing={3}>
                <Text>
                  Are you sure you want to revoke the API key &quot;{mgmt.keyToRevoke?.key_name}
                  &quot;?
                </Text>
                <Box>
                  <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
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
                    <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
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
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button
                ref={cancelRef}
                onClick={mgmt.handleCloseRevokeModal}
                isDisabled={mgmt.isRevoking}
              >
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={mgmt.handleRevokeApiKey}
                ml={3}
                isLoading={mgmt.isRevoking}
                loadingText="Revoking..."
              >
                Revoke
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
}
