import React, { useRef, useEffect } from "react";
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
  useColorModeValue,
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
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Checkbox,
  CheckboxGroup,
} from "@chakra-ui/react";
import { useAuth } from "../../hooks/useAuth";
import { useApiKeyManagementTab } from "./hooks/useApiKeyManagementTab";

export interface ApiKeyManagementTabProps {
  users: import("../../types/auth").User[];
  isLoadingUsers?: boolean;
  /** When true, tab is visible; used to fetch data when user switches to this tab */
  isActive?: boolean;
}

export default function ApiKeyManagementTab({
  users,
  isActive = false,
}: ApiKeyManagementTabProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { user } = useAuth();
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const mgmt = useApiKeyManagementTab({
    user: user ?? null,
    users,
    isLoadingUsers: false,
  });

  useEffect(() => {
    if (isActive) {
      mgmt.handleFetchAllApiKeys();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive]);

  return (
    <>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="gray.700" userSelect="none" cursor="default">
              API Key Management
            </Heading>
            <Button
              size="sm"
              colorScheme="blue"
              onClick={mgmt.handleFetchAllApiKeys}
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
              <HStack justify="space-between" mb={4}>
                <Heading size="sm" color="gray.700" userSelect="none" cursor="default">
                  Filters
                </Heading>
                <Button
                  size="sm"
                  variant="outline"
                  colorScheme="gray"
                  onClick={mgmt.handleResetFilters}
                  isDisabled={
                    mgmt.filterUser === "all" &&
                    mgmt.filterPermission === "all" &&
                    mgmt.filterActive === "all"
                  }
                >
                  Reset Filters
                </Button>
              </HStack>
              <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
                <FormControl>
                  <FormLabel fontWeight="semibold">Filter by User</FormLabel>
                  <Select
                    value={mgmt.filterUser}
                    onChange={(e) => mgmt.setFilterUser(e.target.value)}
                    bg="white"
                  >
                    <option value="all">All Users</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id.toString()}>
                        {u.email} ({u.username})
                      </option>
                    ))}
                  </Select>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold">Filter by Permission</FormLabel>
                  <Select
                    value={mgmt.filterPermission}
                    onChange={(e) => mgmt.setFilterPermission(e.target.value)}
                    bg="white"
                  >
                    <option value="all">All Permissions</option>
                    {(mgmt.allUniquePermissions.length > 0
                      ? mgmt.allUniquePermissions
                      : mgmt.permissions
                    ).map((perm) => (
                      <option key={perm} value={perm}>
                        {perm}
                      </option>
                    ))}
                  </Select>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight="semibold">Status</FormLabel>
                  <Select
                    value={mgmt.filterActive}
                    onChange={(e) => mgmt.setFilterActive(e.target.value)}
                    bg="white"
                  >
                    <option value="all">All</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </Select>
                </FormControl>
              </SimpleGrid>
            </Box>

            {mgmt.isLoadingAllApiKeys ? (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" color="blue.500" />
                  <Text color="gray.600">Loading API keys...</Text>
                </VStack>
              </Center>
            ) : mgmt.filteredApiKeys.length > 0 ? (
              <TableContainer>
                <Table variant="simple">
                  <Thead>
                    <Tr>
                      <Th>Key Name</Th>
                      <Th>User</Th>
                      <Th>Permissions</Th>
                      <Th>Status</Th>
                      <Th>Created</Th>
                      <Th>Expires</Th>
                      <Th>Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {mgmt.filteredApiKeys.map((key) => (
                      <Tr
                        key={key.id}
                        onClick={() => mgmt.handleOpenViewModal(key)}
                        cursor="pointer"
                        _hover={{ bg: "gray.50" }}
                      >
                        <Td fontWeight="semibold">{key.key_name}</Td>
                        <Td>
                          <VStack align="start" spacing={0}>
                            <Text fontSize="sm">{key.user_email}</Text>
                            <Text fontSize="xs" color="gray.500">
                              {key.username}
                            </Text>
                          </VStack>
                        </Td>
                        <Td>
                          <HStack flexWrap="wrap" spacing={1}>
                            {key.permissions.slice(0, 3).map((perm) => (
                              <Badge key={perm} colorScheme="blue" fontSize="xs">
                                {perm}
                              </Badge>
                            ))}
                            {key.permissions.length > 3 && (
                              <Badge colorScheme="gray" fontSize="xs">
                                +{key.permissions.length - 3}
                              </Badge>
                            )}
                          </HStack>
                        </Td>
                        <Td>
                          <Badge colorScheme={key.is_active ? "green" : "red"}>
                            {key.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </Td>
                        <Td fontSize="sm">
                          {new Date(key.created_at).toLocaleDateString()}
                        </Td>
                        <Td fontSize="sm">
                          {key.expires_at
                            ? new Date(key.expires_at).toLocaleDateString()
                            : "Never"}
                        </Td>
                        <Td>
                          <HStack spacing={2}>
                            <Button
                              size="xs"
                              colorScheme="blue"
                              variant="outline"
                              onClick={(e) => {
                                e.stopPropagation();
                                mgmt.handleOpenViewModal(key);
                              }}
                            >
                              View
                            </Button>
                            <Button
                              size="xs"
                              colorScheme="green"
                              onClick={(e) => {
                                e.stopPropagation();
                                mgmt.handleOpenUpdateModal(key);
                              }}
                            >
                              Update
                            </Button>
                            <Button
                              size="xs"
                              colorScheme="red"
                              variant="outline"
                              onClick={(e) => {
                                e.stopPropagation();
                                mgmt.handleOpenRevokeModal(key);
                              }}
                              isDisabled={!key.is_active}
                            >
                              Revoke
                            </Button>
                          </HStack>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
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
      <Modal
        isOpen={mgmt.isViewModalOpen}
        onClose={mgmt.handleCloseViewModal}
        size="2xl"
        isCentered
      >
        <ModalOverlay />
        <ModalContent maxW="900px" maxH="600px">
          <ModalHeader>API Key Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody overflowY="auto">
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
                    User
                  </Text>
                  <VStack align="start" spacing={0}>
                    <Text fontSize="md">{mgmt.selectedKeyForView.user_email}</Text>
                    <Text fontSize="sm" color="gray.500">
                      @{mgmt.selectedKeyForView.username}
                    </Text>
                  </VStack>
                </Box>
                <Box gridColumn={{ base: "span 1", md: "span 2" }}>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>
                    Permissions
                  </Text>
                  {mgmt.selectedKeyForView.permissions.length > 0 ? (
                    <HStack flexWrap="wrap" spacing={2}>
                      {mgmt.selectedKeyForView.permissions.map((perm) => (
                        <Badge key={perm} colorScheme="blue" fontSize="sm" p={2}>
                          {perm}
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
                    {mgmt.selectedKeyForView.is_active ? "Active" : "Inactive"}
                  </Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                    Created At
                  </Text>
                  <Text fontSize="sm">
                    {new Date(mgmt.selectedKeyForView.created_at).toLocaleString()}
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
                <Box>
                  <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={1}>
                    Key ID
                  </Text>
                  <Text fontSize="sm" fontFamily="mono" color="gray.700">
                    {mgmt.selectedKeyForView.id}
                  </Text>
                </Box>
              </SimpleGrid>
            )}
          </ModalBody>
          <ModalFooter>
            <Button onClick={mgmt.handleCloseViewModal}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Update API Key Modal */}
      <Modal isOpen={mgmt.isUpdateModalOpen} onClose={mgmt.handleCloseUpdateModal} size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Update API Key</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
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
                <FormLabel fontWeight="semibold">Status</FormLabel>
                <Select
                  value={mgmt.updateFormData.is_active ? "active" : "inactive"}
                  onChange={(e) =>
                    mgmt.setUpdateFormData({
                      ...mgmt.updateFormData,
                      is_active: e.target.value === "active",
                    })
                  }
                  bg="white"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </Select>
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
                          <Checkbox key={perm} value={perm} colorScheme="blue">
                            <Text fontSize="sm">{perm}</Text>
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
              {mgmt.selectedKeyForUpdate && (
                <Box>
                  <Text fontSize="sm" fontWeight="semibold" mb={2}>
                    User: {mgmt.selectedKeyForUpdate.user_email}
                  </Text>
                  <Text fontSize="xs" color="gray.500">
                    Key ID: {mgmt.selectedKeyForUpdate.id}
                  </Text>
                </Box>
              )}
            </VStack>
          </ModalBody>
          <ModalFooter>
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
            >
              Update
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

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
                      <strong>User:</strong> {mgmt.keyToRevoke?.user_email} (@
                      {mgmt.keyToRevoke?.username})
                    </Text>
                    <Text>
                      <strong>Key ID:</strong> {mgmt.keyToRevoke?.id}
                    </Text>
                    <Text>
                      <strong>Created:</strong>{" "}
                      {mgmt.keyToRevoke?.created_at
                        ? new Date(mgmt.keyToRevoke.created_at).toLocaleString()
                        : "N/A"}
                    </Text>
                  </VStack>
                </Box>
                {mgmt.keyToRevoke && mgmt.keyToRevoke.permissions.length > 0 && (
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.700" mb={2}>
                      Permissions (will be revoked):
                    </Text>
                    <HStack flexWrap="wrap" spacing={2}>
                      {mgmt.keyToRevoke.permissions.map((perm) => (
                        <Badge key={perm} colorScheme="orange" fontSize="xs">
                          {perm}
                        </Badge>
                      ))}
                    </HStack>
                  </Box>
                )}
                <Alert status="warning" borderRadius="md" mt={2}>
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    This action will disable the API key and make it inactive.
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
