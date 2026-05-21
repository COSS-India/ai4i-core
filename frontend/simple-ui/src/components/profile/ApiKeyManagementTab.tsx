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
  InputGroup,
  InputLeftElement,
  HStack,
  Text,
  VStack,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Select,
  SimpleGrid,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  TableContainer,
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
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useApiKeyManagementTab } from "./hooks/useApiKeyManagementTab";
import { ViewIcon, EditIcon, DeleteIcon, SearchIcon } from "@chakra-ui/icons";
import {
  TableFilterToolbar,
  TablePaginationBar,
  TableSortHeader,
  useAdminTableSurface,
} from "../common/TableControls";
import StandardModal from "../common/StandardModal";
import {
  API_KEY,
  API_KEY_FILTER_STATUS_LIST,
  formatApiKeyActiveLabel,
  formatApiKeyFilterStatusLabel,
} from "../../config/constants";

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
  const { tableBg, tableHeaderBg, tableRowHoverBg, cardBg, borderColor: cardBorder } =
    useAdminTableSurface();

  const mgmt = useApiKeyManagementTab({
    user: user ?? null,
  });

  const [keyNameSortDirection, setKeyNameSortDirection] = useState<"asc" | "desc">("asc");
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(25);
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

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

  const totalApiKeys = sortedApiKeys.length;
  const totalPages = Math.max(1, Math.ceil(totalApiKeys / listPageSize));
  const startRow = totalApiKeys === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const endRow = Math.min(listPage * listPageSize, totalApiKeys);
  const paginatedApiKeys = sortedApiKeys.slice((listPage - 1) * listPageSize, listPage * listPageSize);

  useEffect(() => {
    if (listPage > totalPages) setListPage(totalPages);
  }, [listPage, totalPages]);

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
              loadingText="Loading..."
            >
              Refresh
            </Button>
          </HStack>
        </CardHeader>
        <CardBody>
          <VStack spacing={6} align="stretch">
            <Box>
              <Heading size="sm" color="gray.700" userSelect="none" cursor="default" mb={4}>
                Filters
              </Heading>

              {(() => {
                const hasActiveFilters =
                  mgmt.filterPermission !== "all" ||
                  mgmt.filterActive !== "all" ||
                  mgmt.keyNameSearch.trim() !== "";

                const permissionOptions = mgmt.permissionFilterOptions;

                return (
                  <TableFilterToolbar
                    hasActiveFilters={hasActiveFilters}
                    onClear={() => {
                      mgmt.handleResetFilters();
                      setListPage(1);
                    }}
                    align="flex-end"
                  >
                    <FormControl w={{ base: "full", md: "320px" }}>
                      <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                        Key Name
                      </FormLabel>
                      <InputGroup size="sm">
                        <InputLeftElement pointerEvents="none">
                          <SearchIcon color="gray.400" />
                        </InputLeftElement>
                        <Input
                          value={mgmt.keyNameSearch}
                          onChange={(e) => {
                            mgmt.setKeyNameSearch(e.target.value);
                            setListPage(1);
                          }}
                          placeholder="Search by key name"
                          bg={cardBg}
                        />
                      </InputGroup>
                    </FormControl>

                    <FormControl w={{ base: "full", md: "320px" }}>
                      <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                        Permission
                      </FormLabel>
                      <Select
                        size="sm"
                        value={mgmt.filterPermission}
                        onChange={(e) => {
                          mgmt.setFilterPermission(e.target.value);
                          setListPage(1);
                        }}
                        bg={cardBg}
                      >
                        <option value="all">All Permissions</option>
                        {permissionOptions.map((perm) => (
                          <option key={perm} value={perm}>
                            {perm}
                          </option>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl w={{ base: "full", sm: "160px" }}>
                      <FormLabel fontSize="sm" fontWeight="medium" mb={1}>
                        Status
                      </FormLabel>
                      <Select
                        size="sm"
                        value={mgmt.filterActive}
                        onChange={(e) => {
                          mgmt.setFilterActive(e.target.value);
                          setListPage(1);
                        }}
                        bg={cardBg}
                      >
                        <option value={API_KEY.FILTER_STATUS.ALL}>All</option>
                        {API_KEY_FILTER_STATUS_LIST.map((s) => (
                          <option key={s} value={s}>
                            {formatApiKeyFilterStatusLabel(s)}
                          </option>
                        ))}
                      </Select>
                    </FormControl>
                  </TableFilterToolbar>
                );
              })()}
            </Box>

            {mgmt.isLoadingAllApiKeys ? (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" color="blue.500" />
                  <Text color="gray.600">Loading API keys...</Text>
                </VStack>
              </Center>
            ) : mgmt.filteredApiKeys.length > 0 ? (
              <TableContainer maxH="60vh" overflowY="auto">
                <Table variant="simple" bg={tableBg} size="sm" w="100%">
                  <Thead bg={tableHeaderBg}>
                    <Tr>
                      <Th>
                        <TableSortHeader
                          label="Key Name"
                          direction={keyNameSortDirection}
                          onAsc={() => {
                            setKeyNameSortDirection("asc");
                            setListPage(1);
                          }}
                          onDesc={() => {
                            setKeyNameSortDirection("desc");
                            setListPage(1);
                          }}
                          ascAriaLabel="Sort API keys by name ascending"
                          descAriaLabel="Sort API keys by name descending"
                        />
                      </Th>
                      <Th>Permissions</Th>
                      <Th>Status</Th>
                      <Th>Created</Th>
                      <Th>Expires</Th>
                      <Th>Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {paginatedApiKeys.map((key) => (
                      <Tr
                        key={key.api_key ?? `id-${key.id ?? ""}-${key.user_id}-${key.key_name}`}
                        onClick={() => mgmt.handleOpenViewModal(key)}
                        cursor="pointer"
                        _hover={{ bg: tableRowHoverBg }}
                      >
                        <Td fontWeight="semibold">{key.key_name}</Td>
                        <Td>
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
                        </Td>
                        <Td>
                          <Badge colorScheme={key.is_active ? "green" : "red"}>
                            {formatApiKeyActiveLabel(key.is_active ?? false)}
                          </Badge>
                        </Td>
                        <Td fontSize="sm">
                          {key.created_at
                            ? new Date(key.created_at).toLocaleDateString()
                            : "—"}
                        </Td>
                        <Td fontSize="sm">
                          {key.expires_at
                            ? new Date(key.expires_at).toLocaleDateString()
                            : "Never"}
                        </Td>
                        <Td onClick={(e) => e.stopPropagation()}>
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
                                key.is_active
                                  ? "Update key"
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
                                isDisabled={!key.is_active}
                              />
                            </Tooltip>
                            <Tooltip
                              hasArrow
                              label={key.is_active ? "Revoke key" : "Already revoked"}
                            >
                              <IconButton
                                aria-label="Revoke API key"
                                icon={<DeleteIcon />}
                                size="sm"
                                variant="ghost"
                                colorScheme="red"
                                _hover={{ bg: "red.50" }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  mgmt.handleOpenRevokeModal(key);
                                }}
                                isDisabled={!key.is_active}
                              />
                            </Tooltip>
                          </HStack>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            ) : null}

            {!mgmt.isLoadingAllApiKeys && mgmt.filteredApiKeys.length > 0 ? (
              <TablePaginationBar
                startRow={startRow}
                endRow={endRow}
                totalItems={totalApiKeys}
                page={listPage}
                totalPages={totalPages}
                pageSize={listPageSize}
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                onPageSizeChange={(value) => {
                  setListPageSize(value);
                  setListPage(1);
                }}
                onFirst={() => setListPage(1)}
                onPrev={() => setListPage((p) => Math.max(1, p - 1))}
                onNext={() => setListPage((p) => Math.min(totalPages, p + 1))}
                onLast={() => setListPage(totalPages)}
                canPrev={listPage > 1}
                canNext={listPage < totalPages}
                borderColor={cardBorder}
                bg={cardBg}
              />
            ) : (
              <Alert status="info" borderRadius="md">
                <AlertIcon />
                <AlertDescription>
                  {mgmt.allApiKeys.length === 0
                    ? "No API keys found. Click 'Refresh' to load API keys."
                    : "No API keys match the current filters."}
                </AlertDescription>
              </Alert>
            )}
          </VStack>
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
                    colorScheme={mgmt.selectedKeyForView.is_active ? "green" : "red"}
                    fontSize="sm"
                    p={2}
                  >
                    {formatApiKeyActiveLabel(mgmt.selectedKeyForView.is_active ?? false)}
                  </Badge>
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
                            <Text fontSize="sm">{perm.name}</Text>
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
                          {perm}
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
