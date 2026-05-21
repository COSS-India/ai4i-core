// Tenant Management tab — backed by auth-service tenant endpoints.

import React, { useEffect, useMemo } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Center,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Heading,
  IconButton,
  Input,
  InputGroup,
  InputLeftElement,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  SimpleGrid,
  Spinner,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Table,
  TableContainer,
  Tabs,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tooltip,
  Tr,
  VStack,
} from "@chakra-ui/react";
import {
  FiArrowLeft,
  FiEdit2,
  FiPause,
  FiPlus,
  FiPower,
  FiUserPlus,
  FiUsers,
} from "react-icons/fi";
import { DeleteIcon, EditIcon, SearchIcon, ViewIcon } from "@chakra-ui/icons";
import { useAuth } from "../../hooks/useAuth";
import { useTenantManagement } from "./hooks/useTenantManagement";
import ConfirmDialog from "../common/ConfirmDialog";
import type { TenantStatus, TenantUserStatus, TenantUserView, TenantView } from "../../types/tenant";

const TENANT_STATUS_OPTIONS: TenantStatus[] = ["ACTIVE", "SUSPENDED", "DEACTIVATED"];

function statusColor(status?: string | null): string {
  switch ((status ?? "").toUpperCase()) {
    case "ACTIVE":
      return "green";
    case "SUSPENDED":
      return "orange";
    case "DEACTIVATED":
      return "red";
    case "PENDING":
      return "gray";
    case "INACTIVE":
      return "red";
    default:
      return "gray";
  }
}

function userActiveStatus(u: TenantUserView): TenantUserStatus {
  return u.is_active && (u.is_tenant_active ?? true) ? "ACTIVE" : "INACTIVE";
}

function dash(v?: string | null): string {
  return v && v.trim() ? v : "—";
}

function fmtDate(v?: string | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}

function tenantStatusActionLabel(status: TenantStatus): string {
  switch (status) {
    case "ACTIVE":
      return "Activate";
    case "SUSPENDED":
      return "Suspend";
    case "DEACTIVATED":
      return "Deactivate";
    default:
      return status;
  }
}

export interface TenantManagementTabProps {
  isActive?: boolean;
}

export default function TenantManagementTab({ isActive = false }: TenantManagementTabProps) {
  const { user } = useAuth();
  const tm = useTenantManagement({ user });

  const isAdmin = Boolean(user?.roles?.includes('ADMIN'));

  // Initial fetch when this tab becomes active.
  useEffect(() => {
    if (!isActive || !user) return;
    if (isAdmin) {
      void tm.handleFetchTenants();
    } else {
      void tm.handleFetchTenantUsers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, user, isAdmin]);

  // Refresh users when tenant detail view changes.
  useEffect(() => {
    if (!tm.tenantDetailView) return;
    void tm.handleFetchTenantUsers(tm.tenantDetailView.tenant_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm.tenantDetailView?.tenant_id]);

  const allTenantStatuses = useMemo(
    () =>
      Array.from(new Set(tm.tenants.map((t) => t.status).filter(Boolean))) as TenantStatus[],
    [tm.tenants]
  );

  return (
    <Box>
      {isAdmin && !tm.tenantDetailView && renderAdopterView()}

      {!isAdmin && !tm.tenantDetailView && renderTenantView()}

      {tm.tenantDetailView && renderTenantDetail()}

      {/* Modals always mounted */}
      {renderCreateTenantModal()}
      {renderEditTenantModal()}
      {renderAddUserModal()}
      {renderEditUserModal()}
      {renderViewUserModal()}
      {renderStatusConfirmDialog()}
      {renderDeleteUserDialog()}
    </Box>
  );

  // ── Tenants list (Adopter Admin) ────────────────────────────────────────
  function renderAdopterView() {
    return (
      <Card>
        <CardHeader>
          <HStack justify="space-between" align="center">
            <Heading size="md">Tenants</Heading>
            <HStack>
              <Button
                leftIcon={<FiPlus />}
                size="sm"
                colorScheme="blue"
                onClick={tm.openTenantModal}
              >
                Create Tenant
              </Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <HStack mb={4} spacing={3}>
            <InputGroup maxW="320px">
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search by organisation or tenant ID"
                value={tm.tenantSearch}
                onChange={(e) => tm.setTenantSearch(e.target.value)}
              />
            </InputGroup>
            <Select
              maxW="200px"
              value={tm.tenantFilterStatus}
              onChange={(e) => tm.setTenantFilterStatus(e.target.value)}
            >
              <option value="all">All statuses</option>
              {allTenantStatuses.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
            <Button size="sm" variant="ghost" onClick={tm.handleResetTenantFilters}>
              Reset
            </Button>
          </HStack>

          {tm.isLoadingTenants ? (
            <Center py={8}>
              <Spinner />
            </Center>
          ) : tm.filteredTenants.length === 0 ? (
            <Alert status="info">
              <AlertIcon />
              <AlertDescription>No tenants found.</AlertDescription>
            </Alert>
          ) : (
            <TableContainer>
              <Table variant="simple" size="sm">
                <Thead>
                  <Tr>
                    <Th>Organisation</Th>
                    <Th>Contact</Th>
                    <Th>Email</Th>
                    <Th>Status</Th>
                    <Th>Created</Th>
                    <Th>Actions</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {tm.filteredTenants.map((t) => (
                    <Tr key={t.tenant_id}>
                      <Td>
                        <Button
                          variant="link"
                          colorScheme="blue"
                          onClick={() => tm.handleViewTenant(t)}
                        >
                          {t.organisation}
                        </Button>
                      </Td>
                      <Td>{dash(t.contact_name)}</Td>
                      <Td>{dash(t.email)}</Td>
                      <Td>
                        <Badge colorScheme={statusColor(t.status)}>{t.status}</Badge>
                      </Td>
                      <Td>{fmtDate(t.created_at)}</Td>
                      <Td onClick={(e) => e.stopPropagation()}>
                        {renderTenantRowActions(t)}
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </TableContainer>
          )}
        </CardBody>
      </Card>
    );
  }

  // ── Tenant users list (Tenant Admin or detail view) ─────────────────────
  function renderTenantView() {
    return (
      <Card>
        <CardHeader>
          <HStack justify="space-between" align="center">
            <Heading size="md">Tenant Users</Heading>
            <HStack>
              <Button
                leftIcon={<FiUserPlus />}
                size="sm"
                colorScheme="blue"
                onClick={tm.openUserModal}
              >
                Add User
              </Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>{renderTenantUsersTable()}</CardBody>
      </Card>
    );
  }

  function renderTenantUsersTable() {
    return (
      <>
        <HStack mb={4} spacing={3}>
          <InputGroup maxW="320px">
            <InputLeftElement pointerEvents="none">
              <SearchIcon color="gray.400" />
            </InputLeftElement>
            <Input
              placeholder="Search by username or email"
              value={tm.userSearch}
              onChange={(e) => tm.setUserSearch(e.target.value)}
            />
          </InputGroup>
          <Select
            maxW="200px"
            value={tm.userFilterStatus}
            onChange={(e) => tm.setUserFilterStatus(e.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </Select>
        </HStack>

        {tm.isLoadingTenantUsers ? (
          <Center py={8}>
            <Spinner />
          </Center>
        ) : tm.filteredTenantUsers.length === 0 ? (
          <Alert status="info">
            <AlertIcon />
            <AlertDescription>No users in this tenant.</AlertDescription>
          </Alert>
        ) : (
          <TableContainer>
            <Table variant="simple" size="sm">
              <Thead>
                <Tr>
                  <Th>Username</Th>
                  <Th>Email</Th>
                  <Th>Full Name</Th>
                  <Th>Status</Th>
                  <Th>Created</Th>
                  <Th>Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {tm.filteredTenantUsers.map((u) => (
                  <Tr key={u.user_id}>
                    <Td>
                      <Button
                        variant="link"
                        colorScheme="blue"
                        onClick={() => tm.handleViewUser(u)}
                      >
                        {u.username}
                      </Button>
                    </Td>
                    <Td>{dash(u.email)}</Td>
                    <Td>{dash(u.full_name)}</Td>
                    <Td>
                      <Badge colorScheme={statusColor(userActiveStatus(u))}>
                        {userActiveStatus(u)}
                      </Badge>
                    </Td>
                    <Td>{fmtDate((u as { created_at?: string }).created_at)}</Td>
                    <Td onClick={(e) => e.stopPropagation()}>
                      {renderUserRowActions(u)}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        )}
      </>
    );
  }

  // ── Tenant detail view ──────────────────────────────────────────────────
  function renderTenantDetail() {
    const t = tm.tenantDetailView!;
    return (
      <Card mt={4}>
        <CardHeader>
          <HStack justify="space-between" align="center">
            <HStack>
              <IconButton
                aria-label="Back"
                icon={<FiArrowLeft />}
                size="sm"
                variant="ghost"
                onClick={tm.closeTenantDetailView}
              />
              <Heading size="md">{t.organisation}</Heading>
              <Badge colorScheme={statusColor(t.status)}>{t.status}</Badge>
            </HStack>
            <HStack>
              <Button
                leftIcon={<FiEdit2 />}
                size="sm"
                onClick={() => tm.handleOpenEditTenant(t)}
              >
                Edit
              </Button>
              <Button
                leftIcon={<FiUserPlus />}
                size="sm"
                colorScheme="blue"
                onClick={() => tm.openAddUserForTenant(t.tenant_id)}
              >
                Add User
              </Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <Tabs
            index={tm.tenantDetailSubTab === "overview" ? 0 : 1}
            onChange={(idx) => tm.setTenantDetailSubTab(idx === 0 ? "overview" : "users")}
          >
            <TabList>
              <Tab>Overview</Tab>
              <Tab>
                <FiUsers style={{ marginRight: 6 }} />
                Users
              </Tab>
            </TabList>
            <TabPanels>
              <TabPanel px={0}>
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
                  <Box>
                    <Text fontWeight="semibold">Tenant ID</Text>
                    <Text fontFamily="mono">{t.tenant_id}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Status</Text>
                    <Badge colorScheme={statusColor(t.status)}>{t.status}</Badge>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Contact Name</Text>
                    <Text>{dash(t.contact_name)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Email</Text>
                    <Text>{dash(t.email)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Phone</Text>
                    <Text>{dash(t.phone_number)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Created</Text>
                    <Text>{fmtDate(t.created_at)}</Text>
                  </Box>
                </SimpleGrid>
              </TabPanel>
              <TabPanel px={0}>{renderTenantUsersTable()}</TabPanel>
            </TabPanels>
          </Tabs>
        </CardBody>
      </Card>
    );
  }

  // ── Row actions (inline icons, same pattern as service/model management) ─
  function renderTenantRowActions(t: TenantView) {
    return (
      <HStack spacing={1}>
        <Tooltip label="View" placement="top" hasArrow>
          <IconButton
            aria-label="View tenant"
            icon={<ViewIcon />}
            size="sm"
            variant="ghost"
            colorScheme="blue"
            _hover={{ bg: "blue.50" }}
            onClick={() => tm.handleViewTenant(t)}
          />
        </Tooltip>
        <Tooltip label="Edit" placement="top" hasArrow>
          <IconButton
            aria-label="Edit tenant"
            icon={<EditIcon />}
            size="sm"
            variant="ghost"
            colorScheme="green"
            _hover={{ bg: "green.50" }}
            onClick={() => tm.handleOpenEditTenant(t)}
          />
        </Tooltip>
        {TENANT_STATUS_OPTIONS.filter((s) => s !== t.status).map((s) => (
          <Tooltip
            key={s}
            label={tenantStatusActionLabel(s)}
            placement="top"
            hasArrow
          >
            <IconButton
              aria-label={tenantStatusActionLabel(s)}
              icon={
                s === "ACTIVE" ? (
                  <FiPower />
                ) : s === "SUSPENDED" ? (
                  <FiPause />
                ) : (
                  <DeleteIcon />
                )
              }
              size="sm"
              variant="ghost"
              colorScheme={s === "ACTIVE" ? "green" : s === "SUSPENDED" ? "orange" : "red"}
              _hover={{
                bg: s === "ACTIVE" ? "green.50" : s === "SUSPENDED" ? "orange.50" : "red.50",
              }}
              onClick={() => tm.handleOpenTenantStatus(t, s)}
            />
          </Tooltip>
        ))}
      </HStack>
    );
  }

  function renderUserRowActions(u: TenantUserView) {
    const isActive = userActiveStatus(u) === "ACTIVE";
    return (
      <HStack spacing={1}>
        <Tooltip label="View" placement="top" hasArrow>
          <IconButton
            aria-label="View user"
            icon={<ViewIcon />}
            size="sm"
            variant="ghost"
            colorScheme="blue"
            _hover={{ bg: "blue.50" }}
            onClick={() => tm.handleViewUser(u)}
          />
        </Tooltip>
        <Tooltip label="Edit" placement="top" hasArrow>
          <IconButton
            aria-label="Edit user"
            icon={<EditIcon />}
            size="sm"
            variant="ghost"
            colorScheme="green"
            _hover={{ bg: "green.50" }}
            onClick={() => tm.handleOpenEditUser(u)}
          />
        </Tooltip>
        <Tooltip
          label={isActive ? "Deactivate" : "Activate"}
          placement="top"
          hasArrow
        >
          <IconButton
            aria-label={isActive ? "Deactivate user" : "Activate user"}
            icon={isActive ? <FiPause /> : <FiPower />}
            size="sm"
            variant="ghost"
            colorScheme={isActive ? "orange" : "green"}
            _hover={{ bg: isActive ? "orange.50" : "green.50" }}
            onClick={() =>
              tm.handleOpenUserStatus(u, isActive ? "INACTIVE" : "ACTIVE")
            }
          />
        </Tooltip>
        <Tooltip label="Delete" placement="top" hasArrow>
          <IconButton
            aria-label="Delete user"
            icon={<DeleteIcon />}
            size="sm"
            variant="ghost"
            colorScheme="red"
            _hover={{ bg: "red.50" }}
            onClick={() => tm.handleOpenDeleteUser(u)}
          />
        </Tooltip>
      </HStack>
    );
  }

  // ── Modals ─────────────────────────────────────────────────────────────
  function renderCreateTenantModal() {
    return (
      <Modal isOpen={tm.isTenantModalOpen} onClose={tm.closeTenantModal} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Tenant</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.organisation)} isRequired>
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.tenantForm.organisation}
                  onChange={(e) =>
                    tm.setTenantForm({ ...tm.tenantForm, organisation: e.target.value })
                  }
                />
                <FormErrorMessage>{tm.tenantFormErrors.organisation}</FormErrorMessage>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.contact_name)} isRequired>
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.tenantForm.contact_name}
                  onChange={(e) =>
                    tm.setTenantForm({ ...tm.tenantForm, contact_name: e.target.value })
                  }
                />
                <FormErrorMessage>{tm.tenantFormErrors.contact_name}</FormErrorMessage>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.tenantFormErrors.email)} isRequired>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.tenantForm.email}
                  onChange={(e) =>
                    tm.setTenantForm({ ...tm.tenantForm, email: e.target.value })
                  }
                  onBlur={(e) => tm.checkTenantContactEmailUnique(e.target.value)}
                />
                <FormErrorMessage>{tm.tenantFormErrors.email}</FormErrorMessage>
              </FormControl>
              <FormControl>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.tenantForm.phone_number}
                  onChange={(e) =>
                    tm.setTenantForm({ ...tm.tenantForm, phone_number: e.target.value })
                  }
                />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeTenantModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleRegisterTenant}
              isLoading={tm.isSubmittingTenant}
            >
              Create
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderEditTenantModal() {
    return (
      <Modal
        isOpen={tm.isEditTenantModalOpen}
        onClose={tm.closeEditTenantModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit Tenant</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl isRequired>
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.editTenantForm.organisation ?? ""}
                  onChange={(e) =>
                    tm.setEditTenantForm({
                      ...tm.editTenantForm,
                      organisation: e.target.value,
                    })
                  }
                />
              </FormControl>
              <FormControl>
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.editTenantForm.contact_name ?? ""}
                  onChange={(e) =>
                    tm.setEditTenantForm({
                      ...tm.editTenantForm,
                      contact_name: e.target.value,
                    })
                  }
                />
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.editTenantForm.email ?? ""}
                  onChange={(e) =>
                    tm.setEditTenantForm({
                      ...tm.editTenantForm,
                      email: e.target.value,
                    })
                  }
                />
              </FormControl>
              <FormControl>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editTenantForm.phone_number ?? ""}
                  onChange={(e) =>
                    tm.setEditTenantForm({
                      ...tm.editTenantForm,
                      phone_number: e.target.value,
                    })
                  }
                />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeEditTenantModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditTenant}
              isLoading={tm.isSubmittingEditTenant}
            >
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderAddUserModal() {
    return (
      <Modal isOpen={tm.isUserModalOpen} onClose={tm.closeUserModal} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Add Tenant User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              {isAdmin && (
                <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.tenant_id)}>
                  <FormLabel>Tenant</FormLabel>
                  <Select
                    value={tm.userForm.tenant_id}
                    onChange={(e) => tm.setUserFormTenantId(e.target.value)}
                  >
                    <option value="">Select a tenant…</option>
                    {tm.tenants.map((t) => (
                      <option key={t.tenant_id} value={t.tenant_id}>
                        {t.organisation}
                      </option>
                    ))}
                  </Select>
                  <FormErrorMessage>{tm.userFormErrors.tenant_id}</FormErrorMessage>
                </FormControl>
              )}
              <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.email)}>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.userForm.email}
                  onChange={(e) => tm.setUserForm({ ...tm.userForm, email: e.target.value })}
                  onBlur={(e) => tm.checkUserEmailUnique(e.target.value)}
                />
                <FormErrorMessage>{tm.userFormErrors.email}</FormErrorMessage>
              </FormControl>
              <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.username)}>
                <FormLabel>Username</FormLabel>
                <Input
                  value={tm.userForm.username}
                  onChange={(e) =>
                    tm.setUserForm({ ...tm.userForm, username: e.target.value })
                  }
                />
                <FormErrorMessage>{tm.userFormErrors.username}</FormErrorMessage>
              </FormControl>
              <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.full_name)}>
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.userForm.full_name}
                  onChange={(e) =>
                    tm.setUserForm({ ...tm.userForm, full_name: e.target.value })
                  }
                />
                <FormErrorMessage>{tm.userFormErrors.full_name}</FormErrorMessage>
              </FormControl>
              <FormControl>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.userForm.phone_number}
                  onChange={(e) =>
                    tm.setUserForm({ ...tm.userForm, phone_number: e.target.value })
                  }
                />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeUserModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleRegisterUser}
              isLoading={tm.isSubmittingUser}
            >
              Add
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderEditUserModal() {
    return (
      <Modal
        isOpen={tm.isEditUserModalOpen}
        onClose={tm.closeEditUserModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl isRequired>
                <FormLabel>Username</FormLabel>
                <Input
                  value={tm.editUserForm.username ?? ""}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      username: e.target.value,
                    })
                  }
                />
              </FormControl>
              <FormControl>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.editUserForm.email ?? ""}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      email: e.target.value,
                    })
                  }
                />
              </FormControl>
              <FormControl>
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.editUserForm.full_name ?? ""}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      full_name: e.target.value,
                    })
                  }
                />
              </FormControl>
              <FormControl>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editUserForm.phone_number ?? ""}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      phone_number: e.target.value,
                    })
                  }
                />
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeEditUserModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditUser}
              isLoading={tm.isSubmittingEditUser}
            >
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderViewUserModal() {
    const u = tm.viewUserDetail;
    return (
      <Modal isOpen={tm.isViewUserModalOpen} onClose={tm.closeViewUserModal} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>User Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.isLoadingViewUser ? (
              <Center py={6}>
                <Spinner />
              </Center>
            ) : u ? (
              <VStack align="stretch" spacing={3}>
                <Box>
                  <Text fontWeight="semibold">Username</Text>
                  <Text>{u.username}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">User ID</Text>
                  <Text fontFamily="mono">{u.user_id}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Email</Text>
                  <Text>{dash(u.email)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Full Name</Text>
                  <Text>{dash(u.full_name)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Phone</Text>
                  <Text>{dash(u.phone_number)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Status</Text>
                  <Badge colorScheme={statusColor(userActiveStatus(u))}>
                    {userActiveStatus(u)}
                  </Badge>
                </Box>
              </VStack>
            ) : (
              <Text>No user selected.</Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Button onClick={tm.closeViewUserModal}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderStatusConfirmDialog() {
    const target = tm.statusUpdateTarget;
    const isOpen = tm.isStatusDialogOpen && Boolean(target);
    const targetLabel = target?.type === "tenant" ? "tenant" : "user";
    return (
      <ConfirmDialog
        isOpen={isOpen}
        onClose={tm.closeStatusDialog}
        onConfirm={tm.handleConfirmStatusUpdate}
        title={`Change ${targetLabel} status`}
        body={`Set ${targetLabel} status to "${tm.statusUpdateNewStatus}"?`}
        confirmLabel="Update"
        confirmColorScheme="blue"
        isConfirmLoading={tm.isSubmittingStatus}
      />
    );
  }

  function renderDeleteUserDialog() {
    const target = tm.deleteUserTarget;
    return (
      <ConfirmDialog
        isOpen={tm.isDeleteUserDialogOpen}
        onClose={tm.closeDeleteUserDialog}
        onConfirm={tm.handleConfirmDeleteUser}
        title="Delete user"
        body={`Soft-delete user ${target?.username ?? ""}?`}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={tm.isDeletingUser}
      />
    );
  }
}
