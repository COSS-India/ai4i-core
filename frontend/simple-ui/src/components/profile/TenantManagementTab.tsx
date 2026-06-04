// Tenant Management tab — backed by auth-service tenant endpoints.

import React, { useEffect, useMemo } from "react";
import {
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormErrorMessage,
  FormHelperText,
  FormLabel,
  HStack,
  Heading,
  IconButton,
  Input,
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
  Tabs,
  Center,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import {
  FiArrowLeft,
  FiEdit2,
  FiMail,
  FiPauseCircle,
  FiPlus,
  FiPower,
  FiUserPlus,
  FiUsers,
} from "react-icons/fi";
import { DeleteIcon, EditIcon, ViewIcon } from "@chakra-ui/icons";
import { useAuth } from "../../hooks/useAuth";
import { useTenantManagement } from "./hooks/useTenantManagement";
import ConfirmDialog from "../common/ConfirmDialog";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import TenantUserRoleBadges from "../common/TenantUserRoleBadges";
import { TENANT_USER_ROLE_OPTIONS } from "./types";
import {
  TENANT,
  TENANT_STATUS_LIST,
  TENANT_USER_STATUS_LIST,
  formatTenantStatusLabel,
  formatTenantUserStatusLabel,
  getTenantStatusActionLabel,
  getTenantStatusActionTargets,
  getTenantStatusColorScheme,
  getTenantUserStatusActionLabel,
  getTenantUserStatusToggleTarget,
  isTenantStatus,
  isTenantUserStatus,
  resolveTenantUserDisplayStatus,
} from "../../config/constants";
import type { TenantUserView, TenantView } from "../../types/tenant";

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

  const tenantColumns = useMemo((): AdminTableColumn<TenantView>[] => {
    return [
      {
        id: "organisation",
        header: "Organisation",
        cell: (t) => t.organisation,
      },
      { id: "contact", header: "Contact", cell: (t) => dash(t.contact_name) },
      { id: "email", header: "Email", cell: (t) => dash(t.email) },
      {
        id: "status",
        header: "Status",
        cell: (t) => (
          <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
            {formatTenantStatusLabel(t.status)}
          </Badge>
        ),
      },
      { id: "created", header: "Created", cell: (t) => fmtDate(t.created_at) },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (t) => renderTenantRowActions(t),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm]);

  const userColumns = useMemo((): AdminTableColumn<TenantUserView>[] => {
    return [
      {
        id: "username",
        header: "Username",
        cell: (u) => u.username ?? dash(u.email),
      },
      { id: "email", header: "Email", cell: (u) => dash(u.email) },
      { id: "full_name", header: "Full Name", cell: (u) => dash(u.full_name) },
      {
        id: "roles",
        header: "Role",
        cell: (u) => <TenantUserRoleBadges role={u.role} roles={u.roles} />,
      },
      {
        id: "status",
        header: "Status",
        cell: (u) => (
          <Badge colorScheme={getTenantStatusColorScheme(resolveTenantUserDisplayStatus(u))}>
            {formatTenantUserStatusLabel(resolveTenantUserDisplayStatus(u))}
          </Badge>
        ),
      },
      {
        id: "created",
        header: "Created",
        cell: (u) => fmtDate((u as { created_at?: string }).created_at),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (u) => renderUserRowActions(u),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm]);

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
          <AdminDataTable
            items={tm.filteredTenants}
            columns={tenantColumns}
            getRowKey={(t) => t.tenant_id}
            onRowClick={tm.handleViewTenant}
            isLoading={tm.isLoadingTenants}
            emptyMessage="No tenants found."
            noResultsMessage="No tenants match the current filters."
            unfilteredCount={tm.tenants.length}
            hasActiveFilters={
              tm.tenantFilterStatus !== "all" || tm.tenantSearch.trim() !== ""
            }
            onClearFilters={() => {
              tm.setTenantFilterStatus("all");
              tm.setTenantSearch("");
            }}
            filters={
              <>
                <TableSearchField
                  placeholder="Search by organisation or tenant ID"
                  value={tm.tenantSearch}
                  onChange={tm.setTenantSearch}
                />
                <TableSelectField
                  label="Status"
                  value={tm.tenantFilterStatus}
                  onChange={tm.setTenantFilterStatus}
                  formControlProps={{ w: { base: "full", sm: "200px" } }}
                >
                  <option value="all">All statuses</option>
                  {TENANT_STATUS_LIST.map((s) => (
                    <option key={s} value={s}>
                      {formatTenantStatusLabel(s)}
                    </option>
                  ))}
                </TableSelectField>
              </>
            }
          />
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
      <AdminDataTable
        key={tm.tenantDetailView?.tenant_id ?? "tenant-users"}
        items={tm.filteredTenantUsers}
        columns={userColumns}
        getRowKey={(u) => u.user_id}
        onRowClick={tm.handleViewUser}
        isLoading={tm.isLoadingTenantUsers}
        emptyMessage="No users in this tenant."
        noResultsMessage="No users match the current filters."
        unfilteredCount={tm.tenantUsers.length}
        hasActiveFilters={
          tm.userFilterStatus !== "all" ||
          tm.userFilterRole !== "all" ||
          tm.userSearch.trim() !== ""
        }
        onClearFilters={tm.handleResetUserFilters}
        filters={
          <>
            <TableSearchField
              placeholder="Search by username, email, or full name"
              value={tm.userSearch}
              onChange={tm.setUserSearch}
            />
            <TableSelectField
              label="Status"
              value={tm.userFilterStatus}
              onChange={tm.setUserFilterStatus}
              formControlProps={{ w: { base: "full", sm: "200px" } }}
            >
              <option value="all">All statuses</option>
              {TENANT_USER_STATUS_LIST.map((s) => (
                <option key={s} value={s}>
                  {formatTenantUserStatusLabel(s)}
                </option>
              ))}
            </TableSelectField>
            <TableSelectField
              label="Role"
              value={tm.userFilterRole}
              onChange={tm.setUserFilterRole}
              formControlProps={{ w: { base: "full", sm: "200px" } }}
            >
              <option value="all">All roles</option>
              {tm.tenantUserRoleFilterOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </TableSelectField>
          </>
        }
      />
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
              <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
                {formatTenantStatusLabel(t.status)}
              </Badge>
            </HStack>
            <HStack>
              {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
                <Button
                  leftIcon={<FiMail />}
                  size="sm"
                  variant="outline"
                  colorScheme="blue"
                  isLoading={tm.resendVerificationTenantId === t.tenant_id}
                  loadingText="Sending..."
                  onClick={() => void tm.handleResendTenantSetupLink(t)}
                >
                  Resend Setup Link
                </Button>
              )}
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
                    <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
                      {formatTenantStatusLabel(t.status)}
                    </Badge>
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
    const statusActionTargets = getTenantStatusActionTargets(t.status);

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
        {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
          <Tooltip label="Resend setup link" placement="top" hasArrow>
            <IconButton
              aria-label="Resend setup link"
              icon={<FiMail />}
              size="sm"
              variant="ghost"
              colorScheme="blue"
              _hover={{ bg: "blue.50" }}
              isLoading={tm.resendVerificationTenantId === t.tenant_id}
              onClick={() => void tm.handleResendTenantSetupLink(t)}
            />
          </Tooltip>
        )}
        {statusActionTargets.map((s) => (
          <Tooltip
            key={s}
            label={getTenantStatusActionLabel(s, t.status)}
            placement="top"
            hasArrow
          >
            <IconButton
              aria-label={getTenantStatusActionLabel(s, t.status)}
              icon={
                isTenantStatus(s, TENANT.STATUS.ACTIVE) ? (
                  <FiPower />
                ) : isTenantStatus(s, TENANT.STATUS.SUSPENDED) ? (
                  <FiPauseCircle />
                ) : (
                  <DeleteIcon />
                )
              }
              size="sm"
              variant="ghost"
              colorScheme={
                isTenantStatus(s, TENANT.STATUS.ACTIVE)
                  ? "green"
                  : isTenantStatus(s, TENANT.STATUS.SUSPENDED)
                    ? "orange"
                    : "red"
              }
              _hover={{
                bg: isTenantStatus(s, TENANT.STATUS.ACTIVE)
                  ? "green.50"
                  : isTenantStatus(s, TENANT.STATUS.SUSPENDED)
                    ? "orange.50"
                    : "red.50",
              }}
              onClick={() => tm.handleOpenTenantStatus(t, s)}
            />
          </Tooltip>
        ))}
      </HStack>
    );
  }

  function renderUserRowActions(u: TenantUserView) {
    const isActive = isTenantUserStatus(
      resolveTenantUserDisplayStatus(u),
      TENANT.USER_STATUS.ACTIVE
    );
    const statusToggleTarget = getTenantUserStatusToggleTarget(u);
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
        <Tooltip label={getTenantUserStatusActionLabel(u)} placement="top" hasArrow>
          <IconButton
            aria-label={
              isActive ? "Suspend user" : "Activate user"
            }
            icon={isActive ? <FiPauseCircle /> : <FiPower />}
            size="sm"
            variant="ghost"
            colorScheme={isActive ? "orange" : "green"}
            _hover={{ bg: isActive ? "orange.50" : "green.50" }}
            onClick={() => tm.handleOpenUserStatus(u, statusToggleTarget)}
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
                  onChange={(e) => {
                    const value = e.target.value;
                    tm.setTenantForm({ ...tm.tenantForm, email: value });
                    tm.checkTenantContactEmailUnique(value);
                  }}
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
              isDisabled={!tm.canSubmitTenantForm}
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
              <FormControl isRequired isInvalid={Boolean(tm.editTenantFormErrors.email)}>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.editTenantForm.email ?? ""}
                  onChange={(e) => {
                    const value = e.target.value;
                    tm.setEditTenantForm({
                      ...tm.editTenantForm,
                      email: value,
                    });
                    tm.checkEditTenantContactEmailUnique(value);
                  }}
                  onBlur={(e) => tm.checkEditTenantContactEmailUnique(e.target.value)}
                />
                <FormErrorMessage>{tm.editTenantFormErrors.email}</FormErrorMessage>
                <FormHelperText>
                  If you change the contact email, the update takes effect only after the new
                  address is verified.
                </FormHelperText>
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
              isDisabled={!tm.canSubmitEditTenantForm}
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
              {isAdmin && tm.lockedUserFormTenantId && (
                <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.tenant_id)}>
                  <FormLabel>Tenant</FormLabel>
                  <Input
                    value={tm.getLockedUserFormTenantLabel()}
                    isReadOnly
                    bg="gray.50"
                    _dark={{ bg: "whiteAlpha.100" }}
                    cursor="not-allowed"
                  />
                  <FormErrorMessage>{tm.userFormErrors.tenant_id}</FormErrorMessage>
                </FormControl>
              )}
              {isAdmin && !tm.lockedUserFormTenantId && (
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
                  onChange={(e) => {
                    const value = e.target.value;
                    tm.setUserForm({ ...tm.userForm, email: value });
                    tm.checkUserEmailUnique(value);
                  }}
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
              <FormControl isRequired>
                <FormLabel>Role</FormLabel>
                <Select
                  value={tm.userForm.role}
                  onChange={(e) =>
                    tm.setUserForm({
                      ...tm.userForm,
                      role: e.target.value as typeof tm.userForm.role,
                    })
                  }
                >
                  {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
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
              isDisabled={!tm.canSubmitUserForm}
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
                <Text fontSize="md" color="gray.700" py={1}>
                  {dash(tm.editUserRow?.email)}
                </Text>
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Email cannot be changed. Suspend or delete the account if the user has left the
                  organisation.
                </Text>
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
              <FormControl isRequired>
                <FormLabel>Role</FormLabel>
                <Select
                  value={tm.editUserForm.role}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      role: e.target.value as typeof tm.editUserForm.role,
                    })
                  }
                >
                  {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
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
                  <Badge colorScheme={getTenantStatusColorScheme(resolveTenantUserDisplayStatus(u))}>
                    {formatTenantUserStatusLabel(resolveTenantUserDisplayStatus(u))}
                  </Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Roles</Text>
                  <TenantUserRoleBadges role={u.role} roles={u.roles} badgeFontSize="sm" />
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

  function formatStatusConfirmLabel(
    targetType: "tenant" | "user" | undefined,
    status: string
  ): string {
    if (targetType === "user") {
      return formatTenantUserStatusLabel(status);
    }
    return formatTenantStatusLabel(status);
  }

  function renderStatusConfirmDialog() {
    const target = tm.statusUpdateTarget;
    const isOpen = tm.isStatusDialogOpen && Boolean(target);
    const targetLabel = target?.type === "tenant" ? "tenant" : "user";
    const statusLabel = formatStatusConfirmLabel(target?.type, tm.statusUpdateNewStatus);
    return (
      <ConfirmDialog
        isOpen={isOpen}
        onClose={tm.closeStatusDialog}
        onConfirm={tm.handleConfirmStatusUpdate}
        title={`Change ${targetLabel} status`}
        body={`Set ${targetLabel} status to "${statusLabel}"?`}
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
