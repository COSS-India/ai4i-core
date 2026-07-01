// Tenant Management tab — backed by auth-service tenant endpoints.

import React, { useEffect, useMemo, useState } from "react";
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
  FormHelperText,
  FormLabel,
  HStack,
  Heading,
  IconButton,
  Input,
  InputGroup,
  InputLeftAddon,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  SimpleGrid,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Text,
  Tooltip,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { useToast } from "@chakra-ui/react";
import {
  fetchTiers,
  assignTenantTier,
  fetchTenantTiers,
  type TenantTierAssignment,
} from "../../services/tierManagementService";
import {
  FiArrowLeft,
  FiCheckCircle,
  FiEdit2,
  FiMail,
  FiPauseCircle,
  FiPlus,
  FiPower,
  FiUserPlus,
  FiUsers,
} from "react-icons/fi";
import {
  ChevronDownIcon,
  DeleteIcon,
  EditIcon,
  ViewIcon,
} from "@chakra-ui/icons";
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
  getTenantStatusColorScheme,
  isTenantStatus,
  resolveTenantUserDisplayStatus,
} from "../../config/constants";
import { EMAIL_AVAILABLE_MSG } from "../../utils/tenantEmailValidation";
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

const AVATAR_COLORS = [
  "blue.500",
  "green.500",
  "purple.500",
  "teal.500",
  "orange.500",
  "pink.500",
];

function getTenantInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function getTenantAvatarBg(name: string): string {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.codePointAt(i) ?? 0;
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

export default function TenantManagementTab({
  isActive = false,
}: TenantManagementTabProps) {
  const { user } = useAuth();
  const tm = useTenantManagement({ user });

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const userListTenantStatus = tm.activeUserListTenant?.status ?? null;

  const resolveUserDisplayStatus = (u: TenantUserView) =>
    resolveTenantUserDisplayStatus(u, userListTenantStatus);

  const toast = useToast();

  // Assign Tier modal state
  const [assignTierTenant, setAssignTierTenant] = useState<TenantView | null>(
    null,
  );
  const [assignTierId, setAssignTierId] = useState("");
  const [assignBudget, setAssignBudget] = useState("");
  const [assignEffectiveFrom, setAssignEffectiveFrom] = useState("");
  const [assignEffectiveTo, setAssignEffectiveTo] = useState("");
  const [isAssigning, setIsAssigning] = useState(false);
  const [assignTierError, setAssignTierError] = useState<string | null>(null);
  const {
    isOpen: isAssignTierOpen,
    onOpen: onAssignTierOpen,
    onClose: onAssignTierClose,
  } = useDisclosure();

  const tiersQuery = useQuery({
    queryKey: ["tiers"],
    queryFn: () => fetchTiers(),
    staleTime: 5 * 60_000,
  });
  const tierOptions = tiersQuery.data?.data ?? [];

  const tenantTiersQuery = useQuery({
    queryKey: ["tenant-tiers"],
    queryFn: () => fetchTenantTiers(),
    staleTime: 2 * 60_000,
    enabled: isAdmin,
  });
  const tenantTierAssignments = tenantTiersQuery.data?.data ?? [];
  const tierAssignedTenantIds = useMemo(
    () => new Set(tenantTierAssignments.map((a) => String(a.tenant_id))),
    [tenantTierAssignments],
  );

  const [viewTierTenant, setViewTierTenant] =
    useState<TenantTierAssignment | null>(null);
  const {
    isOpen: isViewTierOpen,
    onOpen: onViewTierOpen,
    onClose: onViewTierClose,
  } = useDisclosure();

  const handleOpenAssignTier = (t: TenantView) => {
    setAssignTierTenant(t);
    setAssignTierId("");
    setAssignBudget("");
    setAssignEffectiveFrom("");
    setAssignEffectiveTo("");
    setAssignTierError(null);
    onAssignTierOpen();
  };

  const handleAssignTierClose = () => {
    if (isAssigning) return;
    onAssignTierClose();
    setAssignTierTenant(null);
    setAssignEffectiveFrom("");
    setAssignEffectiveTo("");
    setAssignTierError(null);
  };

  const handleAssignTierSubmit = async () => {
    if (
      !assignTierTenant ||
      !assignTierId ||
      !assignBudget.trim() ||
      !assignEffectiveFrom ||
      !assignEffectiveTo
    )
      return;
    setIsAssigning(true);
    setAssignTierError(null);
    try {
      await assignTenantTier({
        tenant_id: String(assignTierTenant.tenant_id),
        tier_id: assignTierId,
        budget: Number(assignBudget),
        effective_from: new Date(assignEffectiveFrom).toISOString(),
        effective_to: new Date(assignEffectiveTo).toISOString(),
      });
      toast({
        title: "Tier assigned",
        description: `Tier assigned to "${assignTierTenant.organisation}" successfully.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      onAssignTierClose();
      setAssignTierTenant(null);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      const message =
        (typeof detail === "object" && detail !== null
          ? detail.message
          : detail) ??
        err?.message ??
        "An error occurred.";
      setAssignTierError(String(message));
    } finally {
      setIsAssigning(false);
    }
  };

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
        header: "Tenant",
        cell: (t) => (
          <HStack spacing={3}>
            <Center
              w={8}
              h={8}
              borderRadius="full"
              bg={getTenantAvatarBg(t.organisation)}
              color="white"
              fontSize="xs"
              fontWeight="bold"
              flexShrink={0}
            >
              {getTenantInitials(t.organisation)}
            </Center>
            <Text fontWeight="medium" fontSize="sm">
              {t.organisation}
            </Text>
          </HStack>
        ),
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
      {
        id: "created",
        header: "Onboarded",
        cell: (t) => fmtDate(t.created_at),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (t) => renderTenantRowActions(t),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm, tierOptions]);

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
          <Badge
            colorScheme={getTenantStatusColorScheme(
              resolveUserDisplayStatus(u),
            )}
          >
            {formatTenantUserStatusLabel(resolveUserDisplayStatus(u))}
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
        header: "",
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
      {renderAssignTierModal()}
      {renderViewTierModal()}
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
                  onClick={() => void tm.handleResendTenantVerificationEmail(t)}
                >
                  Resend Verification Email
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
            onChange={(idx) =>
              tm.setTenantDetailSubTab(idx === 0 ? "overview" : "users")
            }
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
                {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
                  <Alert
                    status="info"
                    variant="left-accent"
                    borderRadius="md"
                    mb={4}
                  >
                    <AlertIcon />
                    <Box flex="1">
                      <AlertDescription fontSize="sm">
                        This tenant is awaiting activation. The contact must
                        complete the email verification link. If the link
                        expired or was not received, resend it below.
                      </AlertDescription>
                      <Button
                        mt={3}
                        size="sm"
                        leftIcon={<FiMail />}
                        colorScheme="blue"
                        variant="outline"
                        isLoading={
                          tm.resendVerificationTenantId === t.tenant_id
                        }
                        loadingText="Sending..."
                        onClick={() =>
                          void tm.handleResendTenantVerificationEmail(t)
                        }
                      >
                        Resend Verification Email
                      </Button>
                    </Box>
                  </Alert>
                )}
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
  type RowActionMenuItem = {
    key: string;
    label: string;
    onSelect: () => void;
    color: string;
    hoverBg: string;
    icon: React.ReactNode;
    isDisabled?: boolean;
  };

  function renderOverflowActionMenu(
    items: RowActionMenuItem[],
    stopRowClick: (e: React.MouseEvent) => void,
    menuAriaLabel: string,
  ) {
    return (
      <Menu>
        <MenuButton
          as={IconButton}
          aria-label={menuAriaLabel}
          icon={<ChevronDownIcon />}
          size="sm"
          variant="ghost"
          colorScheme="gray"
          _hover={{ bg: "gray.100" }}
          onClick={stopRowClick}
        />
        <MenuList minW="auto" w="auto" py={1}>
          {items.map((item) => (
            <Tooltip
              key={item.key}
              label={item.label}
              placement="left"
              hasArrow
              openDelay={300}
            >
              <MenuItem
                aria-label={item.label}
                color={item.color}
                _hover={{ bg: item.hoverBg }}
                isDisabled={item.isDisabled}
                px={2}
                py={2}
                minH="8"
                w="auto"
                onClick={(e) => {
                  stopRowClick(e);
                  item.onSelect();
                }}
              >
                {item.icon}
              </MenuItem>
            </Tooltip>
          ))}
        </MenuList>
      </Menu>
    );
  }

  function renderTenantRowActions(t: TenantView) {
    const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();

    const items: RowActionMenuItem[] = (() => {
      if (isTenantStatus(t.status, TENANT.STATUS.PENDING)) {
        return [
          {
            key: "resend-verification",
            label: "Resend verification email",
            onSelect: () => void tm.handleResendTenantVerificationEmail(t),
            color: "blue.600",
            hoverBg: "blue.50",
            icon: <FiMail size={16} />,
            isDisabled: tm.resendVerificationTenantId === t.tenant_id,
          },
          {
            key: "deactivate",
            label: "Deactivate",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      if (isTenantStatus(t.status, TENANT.STATUS.ACTIVE)) {
        return [
          {
            key: "suspend",
            label: "Suspend",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.SUSPENDED),
            color: "orange.600",
            hoverBg: "orange.50",
            icon: <FiPauseCircle size={16} />,
          },
          {
            key: "deactivate",
            label: "Deactivate",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      if (isTenantStatus(t.status, TENANT.STATUS.SUSPENDED)) {
        return [
          {
            key: "activate",
            label: "Activate",
            onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
            color: "green.600",
            hoverBg: "green.50",
            icon: <FiPower size={16} />,
          },
          {
            key: "deactivate",
            label: "Deactivate",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      // DEACTIVATED
      return [
        {
          key: "activate",
          label: "Activate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
          color: "green.600",
          hoverBg: "green.50",
          icon: <FiPower size={16} />,
        },
      ];
    })();

    return (
      <HStack spacing={2}>
        <IconButton
          aria-label="View tenant"
          icon={<ViewIcon />}
          size="sm"
          variant="ghost"
          colorScheme="blue"
          _hover={{ bg: "blue.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleViewTenant(t);
          }}
        />
        <IconButton
          aria-label="Edit tenant"
          icon={<EditIcon />}
          size="sm"
          variant="ghost"
          colorScheme="green"
          _hover={{ bg: "green.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleOpenEditTenant(t);
          }}
        />
        {tierAssignedTenantIds.has(String(t.tenant_id)) ? (
          <Tooltip label="View Tier">
            <IconButton
              aria-label="View tier"
              icon={<FiCheckCircle size={14} />}
              size="xs"
              w={4}
              h={4}
              minW={4}
              variant="outline"
              colorScheme="green"
              borderRadius="full"
              _hover={{ bg: "green.50" }}
              onClick={(e) => {
                stopRowClick(e);
                const assignment =
                  tenantTierAssignments.find(
                    (a) => String(a.tenant_id) === String(t.tenant_id),
                  ) ?? null;
                setViewTierTenant(assignment);
                onViewTierOpen();
              }}
            />
          </Tooltip>
        ) : (
          <Tooltip label="Assign Tier">
            <IconButton
              aria-label="Assign tier"
              icon={<FiPlus size={8} />}
              size="xs"
              w={4}
              h={4}
              minW={4}
              variant="outline"
              colorScheme="blue"
              borderRadius="full"
              _hover={{ bg: "blue.50" }}
              onClick={(e) => {
                stopRowClick(e);
                handleOpenAssignTier(t);
              }}
            />
          </Tooltip>
        )}

        {renderOverflowActionMenu(items, stopRowClick, "Tenant actions")}
      </HStack>
    );
  }

  function renderUserRowActions(u: TenantUserView) {
    const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();
    const displayStatus = resolveUserDisplayStatus(u);

    const items: RowActionMenuItem[] = (() => {
      if (
        displayStatus === TENANT.USER_STATUS.PENDING ||
        displayStatus === TENANT.USER_STATUS.PENDING_ACTIVATION
      ) {
        return [
          {
            key: "resend-verification",
            label: "Resend verification email",
            onSelect: () => void tm.handleResendTenantUserVerification(u),
            color: "blue.600",
            hoverBg: "blue.50",
            icon: <FiMail size={16} />,
            isDisabled: tm.resendVerificationUserId === u.user_id,
          },
          {
            key: "delete",
            label: "Delete",
            onSelect: () => tm.handleOpenDeleteUser(u),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      if (displayStatus === TENANT.USER_STATUS.ACTIVE) {
        return [
          {
            key: "suspend",
            label: "Suspend",
            onSelect: () =>
              tm.handleOpenUserStatus(u, TENANT.USER_STATUS.SUSPENDED),
            color: "orange.600",
            hoverBg: "orange.50",
            icon: <FiPauseCircle size={16} />,
          },
          {
            key: "delete",
            label: "Delete",
            onSelect: () => tm.handleOpenDeleteUser(u),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      // SUSPENDED
      return [
        {
          key: "activate",
          label: "Activate",
          onSelect: () => tm.handleOpenUserStatus(u, TENANT.USER_STATUS.ACTIVE),
          color: "green.600",
          hoverBg: "green.50",
          icon: <FiPower size={16} />,
        },
        {
          key: "delete",
          label: "Delete",
          onSelect: () => tm.handleOpenDeleteUser(u),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
    })();

    return (
      <HStack spacing={2}>
        <IconButton
          aria-label="View user"
          icon={<ViewIcon />}
          size="sm"
          variant="ghost"
          colorScheme="blue"
          _hover={{ bg: "blue.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleViewUser(u);
          }}
        />
        <IconButton
          aria-label="Edit user"
          icon={<EditIcon />}
          size="sm"
          variant="ghost"
          colorScheme="green"
          _hover={{ bg: "green.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleOpenEditUser(u);
          }}
        />

        {renderOverflowActionMenu(items, stopRowClick, "User actions")}
      </HStack>
    );
  }

  // ── Modals ─────────────────────────────────────────────────────────────
  function renderCreateTenantModal() {
    return (
      <Modal
        isOpen={tm.isTenantModalOpen}
        onClose={tm.closeTenantModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create Tenant</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.organisation)}
                isRequired
              >
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.tenantForm.organisation}
                  onChange={(e) =>
                    tm.handleTenantOrganisationChange(e.target.value)
                  }
                  onBlur={(e) =>
                    tm.handleTenantOrganisationBlur(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.tenantFormErrors.organisation}
                </FormErrorMessage>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.contact_name)}
                isRequired
              >
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.tenantForm.contact_name}
                  onChange={(e) =>
                    tm.handleTenantContactNameChange(e.target.value)
                  }
                  onBlur={(e) =>
                    tm.handleTenantContactNameBlur(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.tenantFormErrors.contact_name}
                </FormErrorMessage>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.email)}
                isRequired
              >
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.tenantForm.email}
                  onChange={(e) => tm.handleTenantEmailChange(e.target.value)}
                />
                <FormErrorMessage>{tm.tenantFormErrors.email}</FormErrorMessage>
                {tm.tenantEmailStatus === "checking" &&
                  !tm.tenantFormErrors.email && (
                    <FormHelperText color="gray.500">
                      Checking if email exists…
                    </FormHelperText>
                  )}
                {tm.tenantEmailStatus === "available" &&
                  !tm.tenantFormErrors.email && (
                    <FormHelperText color="green.600">
                      {EMAIL_AVAILABLE_MSG}
                    </FormHelperText>
                  )}
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.phone_number)}
              >
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.tenantForm.phone_number}
                  onChange={(e) => tm.handleTenantPhoneChange(e.target.value)}
                />
                <FormErrorMessage>
                  {tm.tenantFormErrors.phone_number}
                </FormErrorMessage>
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
              <FormControl
                isRequired
                isInvalid={Boolean(tm.editTenantFormErrors.organisation)}
              >
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.editTenantForm.organisation ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantOrganisationChange(e.target.value)
                  }
                  onBlur={(e) =>
                    tm.handleEditTenantOrganisationBlur(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.organisation}
                </FormErrorMessage>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.editTenantFormErrors.contact_name)}
              >
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.editTenantForm.contact_name ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantContactNameChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.contact_name}
                </FormErrorMessage>
              </FormControl>
              <FormControl
                isRequired
                isInvalid={Boolean(tm.editTenantFormErrors.email)}
              >
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.editTenantForm.email ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantEmailChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.email}
                </FormErrorMessage>
                {tm.editTenantEmailStatus === "checking" &&
                  !tm.editTenantFormErrors.email && (
                    <FormHelperText color="gray.500">
                      Checking if email exists…
                    </FormHelperText>
                  )}
                {tm.editTenantEmailStatus === "available" &&
                  !tm.editTenantFormErrors.email && (
                    <FormHelperText color="green.600">
                      {EMAIL_AVAILABLE_MSG}
                    </FormHelperText>
                  )}
                <FormHelperText>
                  If you change the contact email, the update takes effect only
                  after the new address is verified.
                </FormHelperText>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.editTenantFormErrors.phone_number)}
              >
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editTenantForm.phone_number ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantPhoneChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.phone_number}
                </FormErrorMessage>
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
                <FormControl
                  isRequired
                  isInvalid={Boolean(tm.userFormErrors.tenant_id)}
                >
                  <FormLabel>Tenant</FormLabel>
                  <Input
                    value={tm.getLockedUserFormTenantLabel()}
                    isReadOnly
                    bg="gray.50"
                    _dark={{ bg: "whiteAlpha.100" }}
                    cursor="not-allowed"
                  />
                  <FormErrorMessage>
                    {tm.userFormErrors.tenant_id}
                  </FormErrorMessage>
                </FormControl>
              )}
              {isAdmin && !tm.lockedUserFormTenantId && (
                <FormControl
                  isRequired
                  isInvalid={Boolean(tm.userFormErrors.tenant_id)}
                >
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
                  <FormErrorMessage>
                    {tm.userFormErrors.tenant_id}
                  </FormErrorMessage>
                </FormControl>
              )}
              <FormControl
                isRequired
                isInvalid={Boolean(tm.userFormErrors.email)}
              >
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.userForm.email}
                  onChange={(e) => tm.handleUserEmailChange(e.target.value)}
                />
                <FormErrorMessage>{tm.userFormErrors.email}</FormErrorMessage>
                {tm.userEmailStatus === "checking" &&
                  !tm.userFormErrors.email && (
                    <FormHelperText color="gray.500">
                      Checking if email exists…
                    </FormHelperText>
                  )}
                {tm.userEmailStatus === "available" &&
                  !tm.userFormErrors.email && (
                    <FormHelperText color="green.600">
                      {EMAIL_AVAILABLE_MSG}
                    </FormHelperText>
                  )}
              </FormControl>
              <FormControl
                isRequired
                isInvalid={Boolean(tm.userFormErrors.full_name)}
              >
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.userForm.full_name}
                  onChange={(e) => tm.handleUserFullNameChange(e.target.value)}
                />
                <FormErrorMessage>
                  {tm.userFormErrors.full_name}
                </FormErrorMessage>
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
              <FormControl isInvalid={Boolean(tm.userFormErrors.phone_number)}>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.userForm.phone_number}
                  onChange={(e) => tm.handleUserPhoneChange(e.target.value)}
                />
                <FormErrorMessage>
                  {tm.userFormErrors.phone_number}
                </FormErrorMessage>
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
              <FormControl
                isRequired
                isInvalid={Boolean(tm.editUserFormErrors.username)}
              >
                <FormLabel>Username</FormLabel>
                <Input
                  value={tm.editUserForm.username ?? ""}
                  onChange={(e) =>
                    tm.handleEditUserUsernameChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editUserFormErrors.username}
                </FormErrorMessage>
              </FormControl>
              <FormControl>
                <FormLabel>Email</FormLabel>
                <Text fontSize="md" color="gray.700" py={1}>
                  {dash(tm.editUserRow?.email)}
                </Text>
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Email cannot be changed. Suspend or delete the account if the
                  user has left the organisation.
                </Text>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.editUserFormErrors.full_name)}>
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.editUserForm.full_name ?? ""}
                  onChange={(e) =>
                    tm.handleEditUserFullNameChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editUserFormErrors.full_name}
                </FormErrorMessage>
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
              <FormControl
                isInvalid={Boolean(tm.editUserFormErrors.phone_number)}
              >
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editUserForm.phone_number ?? ""}
                  onChange={(e) => tm.handleEditUserPhoneChange(e.target.value)}
                />
                <FormErrorMessage>
                  {tm.editUserFormErrors.phone_number}
                </FormErrorMessage>
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
              isDisabled={!tm.canSubmitEditUserForm}
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
      <Modal
        isOpen={tm.isViewUserModalOpen}
        onClose={tm.closeViewUserModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>User Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {u ? (
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
                  <Badge
                    colorScheme={getTenantStatusColorScheme(
                      resolveUserDisplayStatus(u),
                    )}
                  >
                    {formatTenantUserStatusLabel(resolveUserDisplayStatus(u))}
                  </Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Roles</Text>
                  <TenantUserRoleBadges
                    role={u.role}
                    roles={u.roles}
                    badgeFontSize="sm"
                  />
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
    status: string,
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
    const statusLabel = formatStatusConfirmLabel(
      target?.type,
      tm.statusUpdateNewStatus,
    );
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

  function renderAssignTierModal() {
    const tenant = assignTierTenant;
    const canAssign =
      !!assignTierId &&
      !!assignBudget.trim() &&
      !!assignEffectiveFrom &&
      !!assignEffectiveTo;
    return (
      <Modal
        isOpen={isAssignTierOpen}
        onClose={handleAssignTierClose}
        isCentered
        size="xl"
      >
        <ModalOverlay />
        <ModalContent minH="350px">
          <ModalHeader fontSize="md" fontWeight="semibold" pb={1}>
            Assign Tier{tenant ? ` — ${tenant.organisation}` : ""}
          </ModalHeader>
          <ModalCloseButton isDisabled={isAssigning} />
          <ModalBody pb={6}>
            <VStack align="stretch" spacing={5}>
              {assignTierError && (
                <Alert status="error" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    {assignTierError}
                  </AlertDescription>
                </Alert>
              )}
              <FormControl isRequired>
                <FormLabel fontWeight="semibold" fontSize="sm">
                  Tier
                </FormLabel>
                <Select
                  value={assignTierId}
                  onChange={(e) => setAssignTierId(e.target.value)}
                  placeholder="Select a tier"
                  size="sm"
                  isDisabled={isAssigning}
                >
                  {tierOptions.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>
              </FormControl>

              <FormControl isRequired>
                <FormLabel fontWeight="semibold" fontSize="sm">
                  Budget
                </FormLabel>
                <InputGroup size="sm">
                  <InputLeftAddon>₹</InputLeftAddon>
                  <Input
                    value={assignBudget}
                    onChange={(e) => setAssignBudget(e.target.value)}
                    placeholder="e.g. 500000"
                    type="number"
                    min={0}
                    isDisabled={isAssigning}
                  />
                </InputGroup>
              </FormControl>

              <HStack spacing={4} align="flex-start">
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">
                    Effective From
                  </FormLabel>
                  <Input
                    type="date"
                    size="sm"
                    value={assignEffectiveFrom}
                    onChange={(e) => setAssignEffectiveFrom(e.target.value)}
                    isDisabled={isAssigning}
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel fontWeight="semibold" fontSize="sm">
                    Effective To
                  </FormLabel>
                  <Input
                    type="date"
                    size="sm"
                    value={assignEffectiveTo}
                    min={assignEffectiveFrom}
                    onChange={(e) => setAssignEffectiveTo(e.target.value)}
                    isDisabled={isAssigning}
                  />
                </FormControl>
              </HStack>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button
              variant="ghost"
              mr={3}
              onClick={handleAssignTierClose}
              isDisabled={isAssigning}
            >
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              isDisabled={!canAssign}
              isLoading={isAssigning}
              loadingText="Assigning..."
              onClick={handleAssignTierSubmit}
            >
              Assign
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderViewTierModal() {
    const a = viewTierTenant;
    return (
      <Modal
        isOpen={isViewTierOpen}
        onClose={() => {
          onViewTierClose();
          setViewTierTenant(null);
        }}
        isCentered
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader fontSize="md" fontWeight="semibold">
            Tier Details
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody pb={6}>
            {a ? (
              <VStack align="stretch" spacing={3}>
                <SimpleGrid columns={2} spacing={3}>
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.500">
                      Tier Name
                    </Text>
                    <Text fontSize="sm">{a.tier_name}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.500">
                      Tenant ID
                    </Text>
                    <Text fontSize="sm" fontFamily="mono">
                      {a.tenant_id}
                    </Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.500">
                      Budget Limit
                    </Text>
                    <Text fontSize="sm">
                      ₹ {parseFloat(a.budget_limit).toLocaleString()}
                    </Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.500">
                      Available Balance
                    </Text>
                    <Text fontSize="sm">
                      ₹ {parseFloat(a.available_balance).toLocaleString()}
                    </Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.500">
                      Effective From
                    </Text>
                    <Text fontSize="sm">{fmtDate(a.effective_from)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold" fontSize="sm" color="gray.500">
                      Effective To
                    </Text>
                    <Text fontSize="sm">{fmtDate(a.effective_to)}</Text>
                  </Box>
                </SimpleGrid>
              </VStack>
            ) : (
              <Text>No tier data available.</Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Button
              onClick={() => {
                onViewTierClose();
                setViewTierTenant(null);
              }}
            >
              Close
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }
}
