// Tenant Management tab view (Multi Tenant Management)
// Uses useTenantManagement for state and handlers; renders tab content + modals.

import React, { useRef, useEffect, useMemo } from "react";
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
  Text,
  VStack,
  HStack,
  useColorModeValue,
  Spinner,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
  Select,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  TableContainer,
  Checkbox,
  CheckboxGroup,
  SimpleGrid,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
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
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  IconButton,
  Tooltip,
} from "@chakra-ui/react";
import { FiBriefcase, FiUsers, FiMoreVertical, FiEye, FiEdit2, FiUserPlus, FiPlayCircle, FiRefreshCw, FiPlus, FiSettings, FiArrowLeft, FiMail, FiPause, FiPower, FiTrash2 } from "react-icons/fi";
import { useAuth } from "../../hooks/useAuth";
import { useTenantManagement } from "./hooks/useTenantManagement";
import { TENANT_USER_ROLE_OPTIONS } from "./types";
import type { TenantUserView } from "../../types/multiTenant";

/** Users table for tenant detail view: filters by tenant and shows search/filters + actions. */
function TenantDetailUsersPanel(props: {
  tenantId: string;
  tenantUsers: TenantUserView[];
  userFilterStatus: string;
  setUserFilterStatus: (v: string) => void;
  userFilterRole: string;
  setUserFilterRole: (v: string) => void;
  userSearch: string;
  setUserSearch: (v: string) => void;
  onViewUser: (u: TenantUserView) => void;
  onManageServices: (u: TenantUserView) => void;
  onEditUser: (u: TenantUserView) => void;
  onUserStatus: (u: TenantUserView, newStatus: "ACTIVE" | "SUSPENDED" | "DEACTIVATED") => void;
  onDeleteUser: (u: TenantUserView) => void;
  TENANT_USER_ROLE_OPTIONS: ReadonlyArray<{ value: string; label: string }>;
}) {
  const {
    tenantId,
    tenantUsers,
    userFilterStatus,
    setUserFilterStatus,
    userFilterRole,
    setUserFilterRole,
    userSearch,
    setUserSearch,
    onViewUser,
    onManageServices,
    onEditUser,
    onUserStatus,
    onDeleteUser,
    TENANT_USER_ROLE_OPTIONS: roleOptions,
  } = props;

  const filtered = useMemo(() => {
    const norm = (s: string | undefined) => String(s ?? "").trim();
    const tenantIdNorm = norm(tenantId);
    let list = tenantUsers.filter((u) => norm(u.tenant_id) === tenantIdNorm);
    if (userFilterStatus !== "all") list = list.filter((u) => u.status === userFilterStatus);
    if (userFilterRole !== "all") list = list.filter((u) => (u.role ?? "") === userFilterRole);
    const search = userSearch.trim().toLowerCase();
    if (search) list = list.filter((u) => (u.username?.toLowerCase().includes(search) || u.email?.toLowerCase().includes(search)));
    return list;
  }, [tenantUsers, tenantId, userFilterStatus, userFilterRole, userSearch]);

  return (
    <VStack align="stretch" spacing={4}>
      <HStack spacing={4} flexWrap="wrap">
        <Input
          placeholder="Search users..."
          size="sm"
          maxW="240px"
          value={userSearch}
          onChange={(e) => setUserSearch(e.target.value)}
          bg="white"
        />
        <Select size="sm" maxW="140px" value={userFilterRole} onChange={(e) => setUserFilterRole(e.target.value)} bg="white">
          <option value="all">All Roles</option>
          {roleOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </Select>
        <Select size="sm" maxW="140px" value={userFilterStatus} onChange={(e) => setUserFilterStatus(e.target.value)} bg="white">
          <option value="all">All Status</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="PENDING">PENDING</option>
          <option value="SUSPENDED">SUSPENDED</option>
          <option value="DEACTIVATED">DEACTIVATED</option>
        </Select>
      </HStack>
      <TableContainer>
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th>NAME</Th>
              <Th>EMAIL</Th>
              <Th>ROLE</Th>
              <Th>LAST LOGIN</Th>
              <Th>STATUS</Th>
              <Th>ACTIONS</Th>
            </Tr>
          </Thead>
          <Tbody>
            {filtered.map((u) => (
              <Tr key={u.id}>
                <Td fontWeight="medium">{u.username || "—"}</Td>
                <Td fontSize="sm">{u.email}</Td>
                <Td><Badge colorScheme="blue" fontSize="xs">{u.role ?? "—"}</Badge></Td>
                <Td fontSize="sm">{u.updated_at ? new Date(u.updated_at).toLocaleString() : "—"}</Td>
                <Td>
                  <Badge colorScheme={u.status === "ACTIVE" ? "green" : u.status === "PENDING" ? "blue" : u.status === "SUSPENDED" ? "orange" : "gray"} fontSize="xs">{u.status}</Badge>
                </Td>
                <Td>
                  <Menu>
                    <MenuButton as={IconButton} icon={<FiMoreVertical />} variant="ghost" size="sm" aria-label="User actions" />
                    <MenuList>
                      <MenuItem icon={<FiEye />} onClick={() => onViewUser(u)}>View</MenuItem>
                      <MenuItem icon={<FiSettings />} onClick={() => onManageServices(u)}>Manage Services</MenuItem>
                      {u.status !== "DEACTIVATED" && (
                        <MenuItem icon={<FiEdit2 />} onClick={() => onEditUser(u)}>Edit</MenuItem>
                      )}
                      {u.status === "ACTIVE" && (
                        <>
                          <MenuItem icon={<FiPause />} onClick={() => onUserStatus(u, "SUSPENDED")}>Suspend</MenuItem>
                          <MenuItem icon={<FiTrash2 />} onClick={() => onDeleteUser(u)}>Delete</MenuItem>
                        </>
                      )}
                      {u.status === "SUSPENDED" && (
                        <>
                          <MenuItem icon={<FiPlayCircle />} onClick={() => onUserStatus(u, "ACTIVE")}>Reactivate</MenuItem>
                          <MenuItem icon={<FiTrash2 />} onClick={() => onDeleteUser(u)}>Delete</MenuItem>
                        </>
                      )}
                      {u.status === "DEACTIVATED" && (
                        <MenuItem icon={<FiPlayCircle />} onClick={() => onUserStatus(u, "ACTIVE")}>Reactivate</MenuItem>
                      )}
                      {u.status === "PENDING" && <MenuItem icon={<FiTrash2 />} onClick={() => onDeleteUser(u)}>Delete</MenuItem>}
                    </MenuList>
                  </Menu>
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </TableContainer>
      <Text fontSize="sm" color="gray.500">Showing {filtered.length} user(s)</Text>
    </VStack>
  );
}

export interface TenantManagementTabProps {
  /** When true, tab is visible; used to fetch data when user switches to this tab */
  isActive?: boolean;
}

export default function TenantManagementTab({ isActive = false }: TenantManagementTabProps) {
  const { user } = useAuth();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const tm = useTenantManagement({ user: user ?? null });

  // When user switches to this tab or subview (Adopter vs Tenant Admin), fetch the right list.
  // In User Management also fetch tenants so "Manage User Services" can resolve tenant subscriptions without calling view/tenant.
  useEffect(() => {
    if (!isActive || !user?.id) return;
    if (tm.multiTenantSubView === "adopter") {
      tm.handleFetchTenants();
    } else {
      tm.handleFetchTenantUsers();
      tm.handleFetchTenants(); // needed so Manage User Services can find tenant subscriptions in User Management
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, tm.multiTenantSubView]);

  // When in tenant detail view on Users tab and list is empty, refetch users (e.g. initial load failed or state not set)
  useEffect(() => {
    if (!isActive || !user?.id || !tm.tenantDetailView || tm.tenantDetailSubTab !== "users") return;
    if (tm.tenantUsers.length === 0) {
      tm.handleFetchTenantUsers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, tm.tenantDetailView?.tenant_id, tm.tenantDetailSubTab]);

  if (!user?.id) return null;
  const showAdopter = user?.is_superuser;
  const showTenant = user?.is_tenant && !user?.is_superuser;

  return (
    <>
      <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px" boxShadow="none">
        <CardHeader>
          <Heading size="md" color="gray.700" userSelect="none" cursor="default" mb={4}>
            {tm.multiTenantSubView === "adopter" ? "Tenant Management" : "User Management"}
          </Heading>
          <HStack spacing={3} mb={4} flexWrap="wrap">
            {!tm.tenantDetailView && (
              <>
                {showAdopter && (
                  <Button
                    size="sm"
                    variant={tm.multiTenantSubView === "adopter" ? "solid" : "outline"}
                    colorScheme="blue"
                    leftIcon={<FiBriefcase />}
                    onClick={() => {
                      tm.setMultiTenantSubView("adopter");
                      tm.handleFetchTenants();
                    }}
                  >
                    Adopter Admin
                  </Button>
                )}
                {showTenant && (
                  <Button
                    size="sm"
                    variant={tm.multiTenantSubView === "tenant" ? "solid" : "outline"}
                    colorScheme="blue"
                    leftIcon={<FiUsers />}
                    onClick={() => {
                      tm.setMultiTenantSubView("tenant");
                      tm.handleFetchTenantUsers();
                    }}
                  >
                    Tenant Admin
                  </Button>
                )}
                <HStack flex={1} justify="flex-end">
                  <Button
                    size="sm"
                    leftIcon={<FiRefreshCw />}
                    onClick={tm.multiTenantSubView === "adopter" ? tm.handleFetchTenants : tm.handleFetchTenantUsers}
                    isLoading={tm.multiTenantSubView === "adopter" ? tm.isLoadingTenants : tm.isLoadingTenantUsers}
                    loadingText="Loading..."
                  >
                    Refresh
                  </Button>
                  {tm.multiTenantSubView === "adopter" ? (
                    <Button size="sm" colorScheme="blue" leftIcon={<FiPlus />} onClick={tm.openTenantModal}>
                      New Tenant
                    </Button>
                  ) : (
                    <Button size="sm" colorScheme="blue" leftIcon={<FiPlus />} onClick={tm.openUserModal}>
                      New User
                    </Button>
                  )}
                </HStack>
              </>
            )}
          </HStack>
          {!tm.tenantDetailView && (
          <Box>
            <Text fontWeight="semibold" color="gray.700" mb={2} fontSize="sm">
              Filters
            </Text>
            <HStack spacing={4} flexWrap="wrap" align="flex-end">
              {tm.multiTenantSubView === "adopter" ? (
                <>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm">Filter by Status</FormLabel>
                    <Select size="sm" value={tm.tenantFilterStatus} onChange={(e) => tm.setTenantFilterStatus(e.target.value)} bg="white">
                      <option value="all">All Status</option>
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="SUSPENDED">SUSPENDED</option>
                      <option value="DEACTIVATED">DEACTIVATED</option>
                    </Select>
                  </FormControl>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm">Filter by Services</FormLabel>
                    <Select size="sm" value={tm.tenantFilterServices} onChange={(e) => tm.setTenantFilterServices(e.target.value)} bg="white">
                      <option value="all">All Services</option>
                      {Array.from(new Set(tm.tenants.flatMap((t) => t.subscriptions || []))).sort().map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl maxW="240px">
                    <FormLabel fontSize="sm">Search by Tenant</FormLabel>
                    <InputGroup size="sm">
                      <Input placeholder="Search tenant name or ID..." value={tm.tenantSearch} onChange={(e) => tm.setTenantSearch(e.target.value)} bg="white" />
                    </InputGroup>
                  </FormControl>
                </>
              ) : (
                <>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm">Filter by Status</FormLabel>
                    <Select size="sm" value={tm.userFilterStatus} onChange={(e) => tm.setUserFilterStatus(e.target.value)} bg="white">
                      <option value="all">All Status</option>
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="PENDING">PENDING</option>
                      <option value="SUSPENDED">SUSPENDED</option>
                      <option value="DEACTIVATED">DEACTIVATED</option>
                    </Select>
                  </FormControl>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm">Filter by Services</FormLabel>
                    <Select size="sm" value={tm.userFilterServices} onChange={(e) => tm.setUserFilterServices(e.target.value)} bg="white">
                      <option value="all">All Services</option>
                      {Array.from(new Set(tm.tenantUsers.flatMap((u) => u.subscriptions || []))).sort().map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </Select>
                  </FormControl>
                                <FormControl maxW="180px">
                                  <FormLabel fontSize="sm">Filter by Role</FormLabel>
                                  <Select size="sm" value={tm.userFilterRole} onChange={(e) => tm.setUserFilterRole(e.target.value)} bg="white">
                                    <option value="all">All Roles</option>
                                    {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                  </Select>
                                </FormControl>
                  <FormControl maxW="240px">
                    <FormLabel fontSize="sm">Search by User</FormLabel>
                    <Input size="sm" placeholder="Search user name or email..." value={tm.userSearch} onChange={(e) => tm.setUserSearch(e.target.value)} bg="white" />
                  </FormControl>
                </>
              )}
              <Button size="sm" variant="link" colorScheme="gray" onClick={tm.handleResetMultiTenantFilters}>
                Reset Filters
              </Button>
            </HStack>
          </Box>
          )}
        </CardHeader>
        <CardBody pt={0}>
          {tm.tenantDetailView ? (
            <VStack align="stretch" spacing={4}>
              <Button
                size="sm"
                variant="link"
                leftIcon={<FiArrowLeft />}
                colorScheme="blue"
                onClick={tm.closeTenantDetailView}
                alignSelf="flex-start"
              >
                Back to Tenant Management
              </Button>
              <HStack spacing={3} flexWrap="wrap" align="center">
                <Heading size="md" color="gray.800">{tm.tenantDetailView.organization_name || tm.tenantDetailView.tenant_id}</Heading>
                <Badge colorScheme={tm.tenantDetailView.status === "ACTIVE" ? "green" : tm.tenantDetailView.status === "SUSPENDED" ? "orange" : tm.tenantDetailView.status === "PENDING" ? "blue" : "gray"} fontSize="sm">
                  {tm.tenantDetailView.status}
                </Badge>
                <Text fontSize="sm" color="gray.600">Tenant ID: {tm.tenantDetailView.tenant_id}</Text>
              </HStack>
              <Tabs
                index={tm.tenantDetailSubTab === "overview" ? 0 : 1}
                onChange={(i) => tm.setTenantDetailSubTab(i === 0 ? "overview" : "users")}
                colorScheme="blue"
                variant="line"
              >
                <TabList>
                  <Tab>Overview</Tab>
                  <Tab>Users</Tab>
                </TabList>
                <TabPanels>
                  <TabPanel px={0}>
                    {tm.isLoadingViewTenant ? (
                      <Center py={8}><Spinner size="lg" color="blue.500" /></Center>
                    ) : tm.viewTenantDetail ? (
                      <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={6}>
                        <Box>
                          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>Tenant Information</Text>
                          <VStack align="stretch" spacing={2} fontSize="sm">
                            <Box><Text color="gray.500">Organization Name</Text><Text fontWeight="medium">{tm.viewTenantDetail.organization_name || "—"}</Text></Box>
                            <Box><Text color="gray.500">Tenant ID</Text><Text fontWeight="medium">{tm.viewTenantDetail.tenant_id}</Text></Box>
                            <Box><Text color="gray.500">Contact Email</Text><Text fontWeight="medium">{tm.viewTenantDetail.email || "—"}</Text></Box>
                            <Box><Text color="gray.500">Domain</Text><Text fontWeight="medium">{tm.viewTenantDetail.domain || "—"}</Text></Box>
                            <Box><Text color="gray.500">Created</Text><Text fontWeight="medium">{tm.viewTenantDetail.created_at ? new Date(tm.viewTenantDetail.created_at).toLocaleString() : "—"}</Text></Box>
                            <Box><Text color="gray.500">Last Updated</Text><Text fontWeight="medium">{tm.viewTenantDetail.updated_at ? new Date(tm.viewTenantDetail.updated_at).toLocaleString() : "—"}</Text></Box>
                          </VStack>
                        </Box>
                        <Box>
                          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>Services Summary</Text>
                          <VStack align="stretch" spacing={1}>
                            {(tm.viewTenantDetail.subscriptions || []).map((s) => (
                              <HStack key={s} justify="space-between">
                                <Text fontSize="sm">{String(s).toUpperCase()}</Text>
                                <Badge colorScheme="green" fontSize="xs">Enabled</Badge>
                              </HStack>
                            ))}
                            {(tm.viewTenantDetail.subscriptions?.length ?? 0) === 0 && (
                              <Text fontSize="sm" color="gray.500">No services enabled</Text>
                            )}
                          </VStack>
                        </Box>
                        <Box>
                          <Text fontWeight="semibold" color="gray.600" fontSize="sm" mb={2}>Status</Text>
                          <HStack spacing={3} align="center">
                            <Badge colorScheme={tm.viewTenantDetail.status === "ACTIVE" ? "green" : tm.viewTenantDetail.status === "SUSPENDED" ? "orange" : tm.viewTenantDetail.status === "PENDING" ? "blue" : "gray"} fontSize="sm">
                              {tm.viewTenantDetail.status}
                            </Badge>
                            {tm.viewTenantDetail.status === "PENDING" && (
                              <Button
                                size="xs"
                                colorScheme="blue"
                                leftIcon={<FiMail />}
                                onClick={() => tm.handleSendVerificationEmail(tm.viewTenantDetail!.tenant_id, tm.viewTenantDetail!.email)}
                                isLoading={tm.sendingVerificationTenantId === tm.viewTenantDetail.tenant_id}
                                loadingText="Sending..."
                              >
                                Send Verification Email
                              </Button>
                            )}
                          </HStack>
                        </Box>
                      </SimpleGrid>
                    ) : (
                      <Text color="gray.500">Failed to load tenant details.</Text>
                    )}
                  </TabPanel>
                  <TabPanel px={0}>
                    <TenantDetailUsersPanel
                      tenantId={tm.tenantDetailView.tenant_id}
                      tenantUsers={tm.tenantUsers}
                      userFilterStatus={tm.userFilterStatus}
                      setUserFilterStatus={tm.setUserFilterStatus}
                      userFilterRole={tm.userFilterRole}
                      setUserFilterRole={tm.setUserFilterRole}
                      userSearch={tm.userSearch}
                      setUserSearch={tm.setUserSearch}
                      onViewUser={tm.handleViewUser}
                      onManageServices={tm.openManageUserServices}
                      onEditUser={tm.handleOpenEditUser}
                      onUserStatus={tm.handleOpenUserStatus}
                      onDeleteUser={tm.handleOpenDeleteUser}
                      TENANT_USER_ROLE_OPTIONS={TENANT_USER_ROLE_OPTIONS}
                    />
                  </TabPanel>
                </TabPanels>
              </Tabs>
            </VStack>
          ) : tm.multiTenantSubView === "adopter" ? (
            tm.isLoadingTenants ? (
              <Center py={8}>
                <VStack spacing={4}>
                  <Spinner size="lg" color="blue.500" />
                  <Text color="gray.600">Loading tenants...</Text>
                </VStack>
              </Center>
            ) : (
              <TableContainer>
                <Table variant="simple" size="sm">
                  <Thead>
                    <Tr>
                      <Th>TENANT NAME</Th>
                      <Th>TENANT ID</Th>
                      <Th>CONTACT</Th>
                      <Th>SERVICES ENABLED</Th>
                      <Th>STATUS</Th>
                      <Th>CREATED</Th>
                      <Th>ACTIONS</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {tm.filteredTenants.map((t) => (
                      <Tr key={t.id}>
                        <Td fontWeight="medium">{t.organization_name || "—"}</Td>
                        <Td>{t.tenant_id || "—"}</Td>
                        <Td><Text fontSize="sm">{t.email}</Text></Td>
                        <Td>
                          <HStack spacing={1} flexWrap="wrap">
                            {(t.subscriptions || []).slice(0, 3).map((s) => (
                              <Badge key={s} colorScheme="blue" fontSize="xs">{String(s).toUpperCase()}</Badge>
                            ))}
                            {(t.subscriptions?.length || 0) > 3 && <Badge colorScheme="gray">+{(t.subscriptions?.length || 0) - 3}</Badge>}
                          </HStack>
                        </Td>
                        <Td>
                          <Badge colorScheme={t.status === "ACTIVE" ? "green" : t.status === "SUSPENDED" ? "orange" : t.status === "PENDING" ? "blue" : "gray"}>{t.status}</Badge>
                        </Td>
                        <Td fontSize="sm">{t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"}</Td>
                        <Td onClick={(e) => e.stopPropagation()}>
                          <Menu>
                            <MenuButton as={IconButton} icon={<FiMoreVertical />} variant="ghost" size="sm" aria-label="Tenant actions" />
                            <MenuList>
                              <MenuItem icon={<FiEye />} onClick={() => tm.handleViewTenant(t)}>View</MenuItem>
                              <MenuItem icon={<FiEdit2 />} onClick={() => tm.handleOpenEditTenant(t)}>Edit</MenuItem>
                              <MenuItem icon={<FiSettings />} onClick={() => tm.openManageServices(t)}>Manage Services</MenuItem>
                              <Tooltip
                                label="Make tenant active to enable Add User"
                                placement="left"
                                isDisabled={t.status === "ACTIVE"}
                              >
                                <Box as="span" display="inline-block">
                                  <MenuItem
                                    icon={<FiUserPlus />}
                                    onClick={() => t.status === "ACTIVE" && tm.openAddUserForTenant(t.tenant_id)}
                                    isDisabled={t.status !== "ACTIVE"}
                                    opacity={t.status !== "ACTIVE" ? 0.6 : 1}
                                  >
                                    Add User
                                  </MenuItem>
                                </Box>
                              </Tooltip>
                              {t.status === "PENDING" && (
                                <MenuItem
                                  icon={<FiMail />}
                                  onClick={() => tm.handleSendVerificationEmail(t.tenant_id, t.email)}
                                  isDisabled={tm.sendingVerificationTenantId === t.tenant_id}
                                >
                                  {tm.sendingVerificationTenantId === t.tenant_id ? "Sending..." : "Send Verification Email"}
                                </MenuItem>
                              )}
                              {t.status === "ACTIVE" && (
                                <>
                                  <MenuItem icon={<FiPause />} onClick={() => tm.handleOpenTenantStatus(t, "SUSPENDED")}>Suspend</MenuItem>
                                  <MenuItem icon={<FiPower />} onClick={() => tm.handleOpenTenantStatus(t, "DEACTIVATED")}>Deactivate</MenuItem>
                                </>
                              )}
                              {t.status === "SUSPENDED" && (
                                <>
                                  <MenuItem icon={<FiPlayCircle />} onClick={() => tm.handleOpenTenantStatus(t, "ACTIVE")}>Reactivate</MenuItem>
                                  <MenuItem icon={<FiPower />} onClick={() => tm.handleOpenTenantStatus(t, "DEACTIVATED")}>Deactivate</MenuItem>
                                </>
                              )}
                              {t.status === "DEACTIVATED" && (
                                <MenuItem icon={<FiPlayCircle />} onClick={() => tm.handleOpenTenantStatus(t, "ACTIVE")}>Reactivate</MenuItem>
                              )}
                            </MenuList>
                          </Menu>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            )
          ) : tm.isLoadingTenantUsers ? (
            <Center py={8}>
              <VStack spacing={4}>
                <Spinner size="lg" color="blue.500" />
                <Text color="gray.600">Loading users...</Text>
              </VStack>
            </Center>
          ) : (
            <TableContainer>
              <Table variant="simple" size="sm">
                <Thead>
                  <Tr>
                    <Th>USER NAME</Th>
                    <Th>EMAIL</Th>
                    <Th>TENANT</Th>
                    <Th>ROLE</Th>
                    <Th>SERVICES ENABLED</Th>
                    <Th>STATUS</Th>
                    <Th>CREATED</Th>
                    <Th>ACTIONS</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {tm.filteredTenantUsers.map((u) => (
                    <Tr key={u.id}>
                      <Td fontWeight="medium">{u.username || "—"}</Td>
                      <Td>{u.email}</Td>
                      <Td fontSize="sm">{u.tenant_id}</Td>
                      <Td fontSize="sm">{u.role ?? "—"}</Td>
                      <Td>
                        <HStack spacing={1} flexWrap="wrap">
                          {(u.subscriptions || []).slice(0, 3).map((s) => (
                            <Badge key={s} colorScheme="blue" fontSize="xs">{String(s).toUpperCase()}</Badge>
                          ))}
                          {(u.subscriptions?.length || 0) > 3 && <Badge colorScheme="gray">+{(u.subscriptions?.length || 0) - 3}</Badge>}
                        </HStack>
                      </Td>
                      <Td>
                        <Badge colorScheme={u.status === "ACTIVE" ? "green" : u.status === "PENDING" ? "blue" : u.status === "SUSPENDED" ? "orange" : "gray"}>{u.status}</Badge>
                      </Td>
                      <Td fontSize="sm">{u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}</Td>
                      <Td onClick={(e) => e.stopPropagation()}>
                        <Menu>
                          <MenuButton as={IconButton} icon={<FiMoreVertical />} variant="ghost" size="sm" aria-label="User actions" />
                          <MenuList>
                            <MenuItem icon={<FiEye />} onClick={() => tm.handleViewUser(u)}>View Details</MenuItem>
                            <MenuItem icon={<FiSettings />} onClick={() => tm.openManageUserServices(u)}>Manage Services</MenuItem>
                            {u.status !== "DEACTIVATED" && (
                              <MenuItem icon={<FiEdit2 />} onClick={() => tm.handleOpenEditUser(u)}>Edit User</MenuItem>
                            )}
                            {u.status === "ACTIVE" && (
                              <>
                                <MenuItem icon={<FiPause />} onClick={() => tm.handleOpenUserStatus(u, "SUSPENDED")}>Suspend User</MenuItem>
                                <MenuItem icon={<FiTrash2 />} onClick={() => tm.handleOpenDeleteUser(u)}>Delete User</MenuItem>
                              </>
                            )}
                            {u.status === "SUSPENDED" && (
                              <>
                                <MenuItem icon={<FiPlayCircle />} onClick={() => tm.handleOpenUserStatus(u, "ACTIVE")}>Reactivate User</MenuItem>
                                <MenuItem icon={<FiTrash2 />} onClick={() => tm.handleOpenDeleteUser(u)}>Delete User</MenuItem>
                              </>
                            )}
                            {u.status === "DEACTIVATED" && (
                              <MenuItem icon={<FiPlayCircle />} onClick={() => tm.handleOpenUserStatus(u, "ACTIVE")}>Reactivate User</MenuItem>
                            )}
                            {u.status === "PENDING" && <MenuItem icon={<FiTrash2 />} onClick={() => tm.handleOpenDeleteUser(u)}>Delete User</MenuItem>}
                          </MenuList>
                        </Menu>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </TableContainer>
          )}
          {!tm.tenantDetailView && tm.multiTenantSubView === "adopter" && !tm.isLoadingTenants && (
            <Text fontSize="sm" color="gray.500" mt={2}>
              Showing {tm.filteredTenants.length} of {tm.tenants.length} tenants
            </Text>
          )}
          {!tm.tenantDetailView && tm.multiTenantSubView === "tenant" && !tm.isLoadingTenantUsers && (
            <Text fontSize="sm" color="gray.500" mt={2}>
              Showing {tm.filteredTenantUsers.length} of {tm.tenantUsers.length} users
            </Text>
          )}
        </CardBody>
      </Card>

      {/* Create New Tenant Modal */}
      <Modal isOpen={tm.isTenantModalOpen} onClose={tm.closeTenantModal} size="lg" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create New Tenant</ModalHeader>
          <ModalCloseButton />
          <Box px={6} pt={2} pb={2}>
            <HStack spacing={2}>
              <Badge colorScheme={tm.tenantModalStep === 1 ? "blue" : "green"} borderRadius="full" px={2}>1</Badge>
              <Badge colorScheme={tm.tenantModalStep === 2 ? "blue" : "gray"} borderRadius="full" px={2}>2</Badge>
            </HStack>
            <Text fontSize="sm" color="gray.600" mt={1}>Step {tm.tenantModalStep} of 2</Text>
          </Box>
          <ModalBody>
            {tm.tenantModalStep === 1 && (
              <VStack spacing={4} align="stretch">
                <FormControl isRequired>
                  <FormLabel>Tenant Organization Name</FormLabel>
                  <Input placeholder="Enter organization name" value={tm.tenantForm.organization_name} onChange={(e) => tm.setTenantForm((f) => ({ ...f, organization_name: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Tenant Domain</FormLabel>
                  <Input placeholder="example.com" value={tm.tenantForm.domain} onChange={(e) => tm.setTenantForm((f) => ({ ...f, domain: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl>
                  <FormLabel>Tenant Contact Name (optional)</FormLabel>
                  <Input placeholder="Enter contact person name (optional)" value={tm.tenantForm.contact_name} onChange={(e) => tm.setTenantForm((f) => ({ ...f, contact_name: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Contact Email</FormLabel>
                  <Input type="email" placeholder="contact@organization.com" value={tm.tenantForm.contact_email} onChange={(e) => tm.setTenantForm((f) => ({ ...f, contact_email: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl>
                  <FormLabel>Contact Phone (optional)</FormLabel>
                  <Input placeholder="+91 XXXXXXXXXX (optional)" value={tm.tenantForm.contact_phone} onChange={(e) => tm.setTenantForm((f) => ({ ...f, contact_phone: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl>
                  <FormLabel>Description (optional)</FormLabel>
                  <Input placeholder="Brief description of the tenant organization" value={tm.tenantForm.description} onChange={(e) => tm.setTenantForm((f) => ({ ...f, description: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl>
                  <FormLabel>Requested subscriptions (optional)</FormLabel>
                  {tm.availableServicesForCreate && tm.availableServicesForCreate.length > 0 ? (
                    <Box borderWidth="1px" borderRadius="md" p={3} bg="white" maxH="200px" overflowY="auto">
                      <Text fontSize="xs" color="gray.500" mb={2}>Select from loaded services:</Text>
                      <CheckboxGroup value={tm.tenantForm.requested_subscriptions || []} onChange={(values) => tm.setTenantForm((f) => ({ ...f, requested_subscriptions: values as string[] }))}>
                        <VStack align="stretch" spacing={2}>
                          {tm.availableServicesForCreate.map((svc) => (
                            <Checkbox key={svc.id} value={svc.service_name} colorScheme="blue" size="sm">
                              <Text fontSize="sm">{(svc.service_name ?? "").toUpperCase()}</Text>
                            </Checkbox>
                          ))}
                        </VStack>
                      </CheckboxGroup>
                    </Box>
                  ) : (
                    <>
                      {/* <Button size="sm" colorScheme="blue" variant="outline" mb={2} onClick={tm.loadServicesForCreateTenant} isLoading={tm.isLoadingServicesForCreate} loadingText="Loading...">
                        Load Services
                      </Button>
                      <Text fontSize="xs" color="gray.500" mb={2}>Load available services from the server, or use the list below.</Text>
                       */}
                      <Box borderWidth="1px" borderRadius="md" p={3} bg="white" maxH="140px" overflowY="auto">
                        <CheckboxGroup value={tm.tenantForm.requested_subscriptions || []} onChange={(values) => tm.setTenantForm((f) => ({ ...f, requested_subscriptions: values as string[] }))}>
                          <SimpleGrid columns={2} spacing={2}>
                            {tm.TENANT_SUBSCRIPTION_OPTIONS.map((opt) => (
                              <Checkbox key={opt.value} value={opt.value} colorScheme="blue" size="sm">{opt.label}</Checkbox>
                            ))}
                          </SimpleGrid>
                        </CheckboxGroup>
                      </Box>
                    </>
                  )}
                  <Text fontSize="xs" color="gray.500">e.g. pipeline, language_detection, tts, asr</Text>
                </FormControl>
                <Text fontSize="sm" color="gray.500">Tenant ID will be auto-generated (e.g. TNT_xxxx).</Text>
              </VStack>
            )}
            {tm.tenantModalStep === 2 && (
              <VStack spacing={4} align="stretch">
                <Box>
                  <Text fontWeight="semibold" fontSize="sm" color="gray.600">Tenant Information</Text>
                  <SimpleGrid columns={2} spacing={2} mt={2} fontSize="sm">
                    <Text><strong>Organization:</strong></Text><Text>{tm.tenantForm.organization_name || "—"}</Text>
                    <Text><strong>Domain:</strong></Text><Text>{tm.tenantForm.domain || "—"}</Text>
                    <Text><strong>Contact Name:</strong></Text><Text>{tm.tenantForm.contact_name || "—"}</Text>
                    <Text><strong>Contact Email:</strong></Text><Text>{tm.tenantForm.contact_email || "—"}</Text>
                    <Text><strong>Phone:</strong></Text><Text>{tm.tenantForm.contact_phone || "—"}</Text>
                    <Text><strong>Tenant ID:</strong></Text><Text>TNT_xxxx (auto-generated)</Text>
                    <Text><strong>Subscriptions:</strong></Text>
                    <Text>{tm.tenantForm.requested_subscriptions?.length ? tm.tenantForm.requested_subscriptions.join(", ") : "None"}</Text>
                  </SimpleGrid>
                </Box>
                <Alert status="info" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription>
                    A verification email will be sent to <strong>{tm.tenantForm.contact_email}</strong>. The tenant will remain in pending status until verified.
                  </AlertDescription>
                </Alert>
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            {tm.tenantModalStep === 1 && (
              <>
                <Button variant="ghost" mr={3} onClick={tm.closeTenantModal}>Cancel</Button>
                <Button colorScheme="blue" onClick={tm.handleTenantStepNext} isDisabled={!tm.tenantForm.organization_name.trim() || !tm.tenantForm.domain.trim() || !tm.tenantForm.contact_email.trim()}>
                  Next &rarr;
                </Button>
              </>
            )}
            {tm.tenantModalStep === 2 && (
              <>
                <Button variant="ghost" mr={3} onClick={tm.handleTenantStepBack} isDisabled={tm.isSubmittingTenant}>&larr; Back</Button>
                <Button variant="ghost" mr={3} onClick={tm.closeTenantModal} isDisabled={tm.isSubmittingTenant}>Cancel</Button>
                <Button colorScheme="blue" onClick={tm.handleRegisterTenant} isLoading={tm.isSubmittingTenant} loadingText="Sending...">
                  Send Verification to Tenant
                </Button>
              </>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Manage Services Modal (existing tenant) */}
      <Modal isOpen={tm.isManageServicesModalOpen} onClose={tm.closeManageServices} size="lg" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Manage Services</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.manageServicesTenant && (
              <>
                <Text fontWeight="semibold" color="gray.700" mb={2}>{tm.manageServicesTenant.organization_name || tm.manageServicesTenant.tenant_id}</Text>
                {tm.isLoadingServices ? (
                  <Center py={10}>
                    <VStack spacing={4}>
                      <Spinner size="lg" color="blue.500" thickness="3px" />
                      <Text fontSize="sm" color="gray.600">Loading available services...</Text>
                      <Text fontSize="xs" color="gray.500">Fetching service list for this tenant</Text>
                    </VStack>
                  </Center>
                ) : tm.availableServices.length === 0 ? (
                  <Box py={4} px={4} borderWidth="1px" borderRadius="lg" borderStyle="dashed" borderColor="gray.300" bg="gray.50">
                    <VStack spacing={4}>
                      <Center>
                        <Box p={3} borderRadius="full" bg="blue.50" color="blue.500">
                          <FiSettings size={28} />
                        </Box>
                      </Center>
                      <Text fontSize="sm" color="gray.700" fontWeight="medium" textAlign="center">
                        Load available services for this tenant
                      </Text>
                      <Text fontSize="sm" color="gray.500" textAlign="center">
                        Services you enable here will be available to users under this tenant.
                      </Text>
                      <Button
                        size="md"
                        colorScheme="blue"
                        leftIcon={<FiRefreshCw />}
                        onClick={tm.loadServicesForManage}
                      >
                        Load Services
                      </Button>
                    </VStack>
                  </Box>
                ) : (
                  <VStack spacing={3} align="stretch">
                    <Text fontSize="sm" color="gray.600">Check to add or uncheck to remove a service for this tenant. Changes are applied immediately.</Text>
                    <Box borderWidth="1px" borderRadius="md" p={3} bg="white" maxH="280px" overflowY="auto">
                      <VStack align="stretch" spacing={2}>
                        {tm.availableServices.map((svc) => (
                          <Checkbox
                            key={svc.id}
                            isChecked={tm.manageServicesSelected.includes(svc.service_name)}
                            onChange={(e) => tm.handleTenantServiceCheckChange(svc.service_name, e.target.checked)}
                            isDisabled={tm.isSavingManageServices}
                            colorScheme="blue"
                            size="sm"
                          >
                            <Text fontSize="sm" fontWeight="medium">{(svc.service_name ?? "").toUpperCase()}</Text>
                          </Checkbox>
                        ))}
                      </VStack>
                    </Box>
                    <Text fontSize="sm" color="gray.500">{tm.manageServicesSelected.length} service(s) selected</Text>
                  </VStack>
                )}
              </>
            )}
          </ModalBody>
          <ModalFooter>
            {tm.availableServices.length > 0 && (
              <>
                <Button variant="ghost" mr={3} onClick={tm.closeManageServices}>Cancel</Button>
                <Button colorScheme="blue" onClick={tm.saveManageServices}>
                  Done
                </Button>
              </>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Manage User Services Modal */}
      <Modal isOpen={tm.isManageUserServicesModalOpen} onClose={tm.closeManageUserServices} size="lg" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Manage User Services</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.manageUserServicesUser && (
              <>
                <Text fontWeight="semibold" color="gray.700" mb={2}>{tm.manageUserServicesUser.username} ({tm.manageUserServicesUser.email})</Text>
                {tm.isLoadingUserServices ? (
                  <Center py={10}>
                    <VStack spacing={4}>
                      <Spinner size="lg" color="blue.500" thickness="3px" />
                      <Text fontSize="sm" color="gray.600">Loading available services...</Text>
                      <Text fontSize="xs" color="gray.500">Fetching services enabled for this user&apos;s tenant</Text>
                    </VStack>
                  </Center>
                ) : tm.availableServicesForUser.length === 0 ? (
                  <Box py={4} px={4} borderWidth="1px" borderRadius="lg" borderStyle="dashed" borderColor="gray.300" bg="gray.50">
                    <VStack spacing={4}>
                      <Center>
                        <Box p={3} borderRadius="full" bg="blue.50" color="blue.500">
                          <FiSettings size={28} />
                        </Box>
                      </Center>
                      <Text fontSize="sm" color="gray.700" fontWeight="medium" textAlign="center">
                        Load available services for this user
                      </Text>
                      <Text fontSize="sm" color="gray.500" textAlign="center">
                        You can only assign services that are enabled for the tenant. Check or uncheck to grant or revoke access.
                      </Text>
                      <Button
                        size="md"
                        colorScheme="blue"
                        leftIcon={<FiRefreshCw />}
                        onClick={tm.loadServicesForUserManage}
                      >
                        Load Services
                      </Button>
                    </VStack>
                  </Box>
                ) : (
                  <VStack spacing={3} align="stretch">
                    <Text fontSize="sm" color="gray.600">Check to add or uncheck to remove a service for this user. Changes are applied immediately.</Text>
                    <Box borderWidth="1px" borderRadius="md" p={3} bg="white" maxH="280px" overflowY="auto">
                      <SimpleGrid columns={{ base: 2, sm: 3, md: 4 }} spacing={2}>
                        {tm.availableServicesForUser.map((svc) => (
                          <Checkbox
                            key={svc.id}
                            isChecked={tm.manageUserServicesSelected.includes(svc.service_name)}
                            onChange={(e) => tm.handleUserServiceCheckChange(svc.service_name, e.target.checked)}
                            isDisabled={tm.isSavingManageUserServices}
                            colorScheme="blue"
                            size="sm"
                          >
                            <Text fontSize="sm" fontWeight="medium">{(svc.service_name ?? "").toUpperCase()}</Text>
                          </Checkbox>
                        ))}
                      </SimpleGrid>
                    </Box>
                    <Text fontSize="sm" color="gray.500">{tm.manageUserServicesSelected.length} service(s) selected</Text>
                  </VStack>
                )}
              </>
            )}
          </ModalBody>
          <ModalFooter>
            {tm.availableServicesForUser.length > 0 && (
              <>
                <Button variant="ghost" mr={3} onClick={tm.closeManageUserServices}>Cancel</Button>
                <Button colorScheme="blue" onClick={tm.saveManageUserServices}>
                  Done
                </Button>
              </>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Add New User Modal */}
      <Modal isOpen={tm.isUserModalOpen} onClose={tm.closeUserModal} size="md" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Add New User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired>
                <FormLabel>Tenant</FormLabel>
                <Select placeholder="Select tenant" value={tm.userForm.tenant_id} onChange={(e) => tm.setUserFormTenantId(e.target.value)} bg="white">
                  {tm.tenants.map((t) => (
                    <option key={t.tenant_id} value={t.tenant_id}>{t.organization_name} ({t.tenant_id})</option>
                  ))}
                </Select>
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Full Name</FormLabel>
                <Input placeholder="Enter user's full name" value={tm.userForm.full_name} onChange={(e) => tm.setUserForm((f) => ({ ...f, full_name: e.target.value }))} bg="white" />
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Email Address</FormLabel>
                <Input type="email" placeholder="user@organization.com" value={tm.userForm.email} onChange={(e) => tm.setUserForm((f) => ({ ...f, email: e.target.value }))} bg="white" />
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Username</FormLabel>
                <Input placeholder="Username (min 3 characters)" value={tm.userForm.username} onChange={(e) => tm.setUserForm((f) => ({ ...f, username: e.target.value }))} bg="white" />
              </FormControl>
              <FormControl>
                <FormLabel>Role</FormLabel>
                <Select value={tm.userForm.role || "USER"} onChange={(e) => tm.setUserForm((f) => ({ ...f, role: e.target.value }))} bg="white">
                  {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel>Services</FormLabel>
                {(() => {
                  const selectedTenant = tm.tenants.find((t) => t.tenant_id === tm.userForm.tenant_id);
                  const tenantServices = selectedTenant?.subscriptions ?? [];
                  if (!tm.userForm.tenant_id) {
                    return <Text fontSize="sm" color="gray.500">Select a tenant to see enabled services.</Text>;
                  }
                  if (tenantServices.length === 0) {
                    return (
                      <Text fontSize="sm" color="orange.600">
                        No services enabled for this tenant. Enable services via Manage Services for the tenant first.
                      </Text>
                    );
                  }
                  return (
                    <CheckboxGroup
                      value={tm.userForm.services}
                      onChange={(values) => tm.setUserForm((f) => ({ ...f, services: values as string[] }))}
                    >
                      <SimpleGrid columns={{ base: 2, sm: 3, md: 4 }} spacing={2}>
                        {tenantServices.map((svc) => (
                          <Checkbox key={svc} value={svc} colorScheme="blue" size="sm">
                            <Text fontSize="sm" fontWeight="medium">{String(svc).toUpperCase()}</Text>
                          </Checkbox>
                        ))}
                      </SimpleGrid>
                    </CheckboxGroup>
                  );
                })()}
              </FormControl>
              <FormControl>
                <Checkbox isChecked={tm.userForm.is_approved} onChange={(e) => tm.setUserForm((f) => ({ ...f, is_approved: e.target.checked }))}>
                  Approved (user can access immediately)
                </Checkbox>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={tm.closeUserModal} isDisabled={tm.isSubmittingUser}>Cancel</Button>
            <Button colorScheme="blue" onClick={tm.handleRegisterUser} isLoading={tm.isSubmittingUser} loadingText="Adding..." isDisabled={!tm.userForm.tenant_id || !tm.userForm.full_name?.trim() || !tm.userForm.email.trim() || !tm.userForm.username.trim() || tm.userForm.username.trim().length < 3}>
              + Add User
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* View Tenant Details Modal */}
      <Modal isOpen={tm.isViewTenantModalOpen} onClose={tm.closeViewTenantModal} size="lg" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Tenant Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.isLoadingViewTenant ? (
              <Center py={6}><Spinner size="lg" color="blue.500" /></Center>
            ) : tm.viewTenantDetail ? (
              <VStack align="stretch" spacing={3}>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Tenant ID</Text><Text>{tm.viewTenantDetail.tenant_id}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Organization</Text><Text>{tm.viewTenantDetail.organization_name || "—"}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Contact Email</Text><Text>{tm.viewTenantDetail.email}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Domain</Text><Text>{tm.viewTenantDetail.domain || "—"}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Status</Text><Badge colorScheme={tm.viewTenantDetail.status === "ACTIVE" ? "green" : tm.viewTenantDetail.status === "SUSPENDED" ? "orange" : "gray"}>{tm.viewTenantDetail.status}</Badge></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Subscriptions</Text><HStack flexWrap="wrap" spacing={1}>{(tm.viewTenantDetail.subscriptions || []).map((s) => <Badge key={s} colorScheme="blue" fontSize="xs">{String(s).toUpperCase()}</Badge>)}</HStack></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Created</Text><Text fontSize="sm">{tm.viewTenantDetail.created_at ? new Date(tm.viewTenantDetail.created_at).toLocaleString() : "—"}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Updated</Text><Text fontSize="sm">{tm.viewTenantDetail.updated_at ? new Date(tm.viewTenantDetail.updated_at).toLocaleString() : "—"}</Text></Box>
              </VStack>
            ) : (
              <Text color="gray.500">No tenant data to display.</Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Button onClick={tm.closeViewTenantModal}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* View User Details Modal */}
      <Modal isOpen={tm.isViewUserModalOpen} onClose={tm.closeViewUserModal} size="md" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>User Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.isLoadingViewUser ? (
              <Center py={6}><Spinner size="lg" color="blue.500" /></Center>
            ) : tm.viewUserDetail ? (
              <VStack align="stretch" spacing={3}>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">User ID</Text><Text>{tm.viewUserDetail.user_id}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Name</Text><Text>{tm.viewUserDetail.username || "—"}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Email</Text><Text>{tm.viewUserDetail.email}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Tenant ID</Text><Text>{tm.viewUserDetail.tenant_id}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Role</Text><Text>{tm.viewUserDetail.role ?? "—"}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Status</Text><Badge colorScheme={tm.viewUserDetail.status === "ACTIVE" ? "green" : tm.viewUserDetail.status === "PENDING" ? "blue" : tm.viewUserDetail.status === "SUSPENDED" ? "orange" : "gray"}>{tm.viewUserDetail.status}</Badge></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Services</Text><HStack flexWrap="wrap" spacing={1}>{(tm.viewUserDetail.subscriptions || []).map((s) => <Badge key={s} colorScheme="blue" fontSize="xs">{String(s).toUpperCase()}</Badge>)}</HStack></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Created</Text><Text fontSize="sm">{tm.viewUserDetail.created_at ? new Date(tm.viewUserDetail.created_at).toLocaleString() : "—"}</Text></Box>
                <Box><Text fontWeight="semibold" color="gray.600" fontSize="sm">Updated</Text><Text fontSize="sm">{tm.viewUserDetail.updated_at ? new Date(tm.viewUserDetail.updated_at).toLocaleString() : "—"}</Text></Box>
              </VStack>
            ) : (
              <Text color="gray.500">No user data to display.</Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Button onClick={tm.closeViewUserModal}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Edit Tenant Modal */}
      <Modal isOpen={tm.isEditTenantModalOpen} onClose={tm.closeEditTenantModal} size="lg" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit Tenant</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.editTenantRow && (
              <VStack align="stretch" spacing={4}>
                <FormControl>
                  <FormLabel>Tenant ID</FormLabel>
                  <Input value={tm.editTenantForm.tenant_id} isReadOnly variant="filled" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Organization Name</FormLabel>
                  <Input value={tm.editTenantForm.organization_name ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, organization_name: e.target.value }))} placeholder="Organization name" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Contact Email</FormLabel>
                  <Input type="email" value={tm.editTenantForm.contact_email ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, contact_email: e.target.value }))} placeholder="contact@example.com" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Domain</FormLabel>
                  <Input value={tm.editTenantForm.domain ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, domain: e.target.value }))} placeholder="example.com" />
                </FormControl>
                {/* <Heading size="sm" pt={2}>Quotas (optional)</Heading>
                <SimpleGrid columns={2} spacing={4}>
                  <FormControl>
                    <FormLabel fontSize="sm">Requested: characters_length</FormLabel>
                    <Input type="number" value={tm.editTenantForm.requested_quotas?.characters_length ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, requested_quotas: { ...f.requested_quotas, characters_length: e.target.value ? Number(e.target.value) : undefined } }))} placeholder="—" />
                  </FormControl>
                  <FormControl>
                    <FormLabel fontSize="sm">Requested: audio_length_in_min</FormLabel>
                    <Input type="number" value={tm.editTenantForm.requested_quotas?.audio_length_in_min ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, requested_quotas: { ...f.requested_quotas, audio_length_in_min: e.target.value ? Number(e.target.value) : undefined } }))} placeholder="—" />
                  </FormControl>
                  <FormControl>
                    <FormLabel fontSize="sm">Usage quota: characters_length</FormLabel>
                    <Input type="number" value={tm.editTenantForm.usage_quota?.characters_length ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, usage_quota: { ...f.usage_quota, characters_length: e.target.value ? Number(e.target.value) : undefined } }))} placeholder="—" />
                  </FormControl>
                  <FormControl>
                    <FormLabel fontSize="sm">Usage quota: audio_length_in_min</FormLabel>
                    <Input type="number" value={tm.editTenantForm.usage_quota?.audio_length_in_min ?? ""} onChange={(e) => tm.setEditTenantForm((f) => ({ ...f, usage_quota: { ...f.usage_quota, audio_length_in_min: e.target.value ? Number(e.target.value) : undefined } }))} placeholder="—" />
                  </FormControl>
                </SimpleGrid> */}
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={tm.closeEditTenantModal} isDisabled={tm.isSubmittingEditTenant}>Cancel</Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditTenant}
              isLoading={tm.isSubmittingEditTenant}
              isDisabled={!tm.editTenantForm.organization_name?.trim() || !tm.editTenantForm.contact_email?.trim() || !tm.editTenantForm.domain?.trim()}
            >
              Save Changes
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Edit User Modal */}
      <Modal isOpen={tm.isEditUserModalOpen} onClose={tm.closeEditUserModal} size="md" isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {tm.editUserRow && (
              <VStack align="stretch" spacing={4}>
                <FormControl>
                  <FormLabel>Tenant ID</FormLabel>
                  <Input value={tm.editUserForm.tenant_id} isReadOnly variant="filled" size="sm" />
                </FormControl>
                <FormControl>
                  <FormLabel>User ID</FormLabel>
                  <Input value={String(tm.editUserForm.user_id)} isReadOnly variant="filled" size="sm" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Username</FormLabel>
                  <Input value={tm.editUserForm.username ?? ""} onChange={(e) => tm.setEditUserForm((f) => ({ ...f, username: e.target.value }))} placeholder="Username" minLength={3} />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Email</FormLabel>
                  <Input type="email" value={tm.editUserForm.email ?? ""} onChange={(e) => tm.setEditUserForm((f) => ({ ...f, email: e.target.value }))} placeholder="user@example.com" />
                </FormControl>
                <FormControl>
                  <FormLabel>Role (optional)</FormLabel>
                  <Select value={tm.editUserForm.role ?? "USER"} onChange={(e) => tm.setEditUserForm((f) => ({ ...f, role: e.target.value }))} bg="white" size="sm">
                    {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </Select>
                </FormControl>
                <FormControl>
                  <FormLabel>Approved (optional)</FormLabel>
                  <Checkbox isChecked={tm.editUserForm.is_approved ?? false} onChange={(e) => tm.setEditUserForm((f) => ({ ...f, is_approved: e.target.checked }))}>
                    User can access immediately
                  </Checkbox>
                </FormControl>
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={tm.closeEditUserModal} isDisabled={tm.isSubmittingEditUser}>Cancel</Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditUser}
              isLoading={tm.isSubmittingEditUser}
              isDisabled={!tm.editUserForm.username?.trim() || tm.editUserForm.username.trim().length < 3 || !tm.editUserForm.email?.trim()}
            >
              Save Changes
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete User Confirmation */}
      <AlertDialog isOpen={tm.isDeleteUserDialogOpen} leastDestructiveRef={cancelRef} onClose={tm.closeDeleteUserDialog}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete user?
            </AlertDialogHeader>
            <AlertDialogBody>
              {tm.deleteUserTarget && (
                <>This will permanently delete the user {tm.deleteUserTarget.username ? `"${tm.deleteUserTarget.username}"` : `(ID ${tm.deleteUserTarget.user_id})`} from the tenant. This action cannot be undone.</>
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={tm.closeDeleteUserDialog} isDisabled={tm.isDeletingUser}>Cancel</Button>
              <Button colorScheme="red" onClick={tm.handleConfirmDeleteUser} ml={3} isLoading={tm.isDeletingUser}>Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Status Update Confirmation */}
      <AlertDialog isOpen={tm.isStatusDialogOpen} leastDestructiveRef={cancelRef} onClose={tm.closeStatusDialog}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Update status to {tm.statusUpdateNewStatus}?
            </AlertDialogHeader>
            <AlertDialogBody>
              {tm.statusUpdateTarget?.type === "tenant" && (
                <>Tenant <strong>{tm.statusUpdateTarget.tenant_id}</strong> will be set to <strong>{tm.statusUpdateNewStatus}</strong>. Current status: {tm.statusUpdateTarget.currentStatus}.</>
              )}
              {tm.statusUpdateTarget?.type === "user" && (
                <>User ID <strong>{tm.statusUpdateTarget.user_id}</strong> (tenant {tm.statusUpdateTarget.tenant_id}) will be set to <strong>{tm.statusUpdateNewStatus}</strong>. Current status: {tm.statusUpdateTarget.currentStatus}.</>
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={tm.closeStatusDialog} isDisabled={tm.isSubmittingStatus}>Cancel</Button>
              <Button colorScheme="orange" onClick={tm.handleConfirmStatusUpdate} ml={3} isLoading={tm.isSubmittingStatus}>Confirm</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </>
  );
}
