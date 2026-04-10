// Tenant Management tab view (Multi Tenant Management)
// Uses useTenantManagement for state and handlers; renders tab content + modals.

import React, { useRef, useEffect, useMemo, useState } from "react";
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
  InputRightElement,
  Text,
  FormErrorMessage,
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
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  IconButton,
  Tooltip,
  useDisclosure,
} from "@chakra-ui/react";
import { FiBriefcase, FiUsers, FiMoreVertical, FiEye, FiEdit2, FiUserPlus, FiPlayCircle, FiRefreshCw, FiPlus, FiSettings, FiArrowLeft, FiMail, FiPause, FiPower, FiTrash2 } from "react-icons/fi";
import { ViewIcon, ViewOffIcon, SearchIcon } from "@chakra-ui/icons";
import { useAuth } from "../../hooks/useAuth";
import { useTenantManagement } from "./hooks/useTenantManagement";
import { TENANT_USER_ROLE_OPTIONS } from "./types";
import ConfirmDialog from "../common/ConfirmDialog";
import { TableFilterToolbar, TablePaginationBar, TableSortHeader } from "../common/TableControls";
import StandardModal from "../common/StandardModal";
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
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
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

  const [userNameSortDirection, setUserNameSortDirection] = useState<"asc" | "desc">("asc");
  const [listPage, setListPage] = useState(1);
  const [listPageSize, setListPageSize] = useState(25);
  const sortedFiltered = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const aName = a.username ?? "";
      const bName = b.username ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return userNameSortDirection === "asc" ? nameCmp : -nameCmp;
      const timeA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const timeB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return timeB - timeA;
    });
  }, [filtered, userNameSortDirection]);

  const totalUsers = sortedFiltered.length;
  const totalPages = Math.max(1, Math.ceil(totalUsers / listPageSize));
  const startRow = totalUsers === 0 ? 0 : (listPage - 1) * listPageSize + 1;
  const endRow = Math.min(listPage * listPageSize, totalUsers);
  const paginatedUsers = sortedFiltered.slice((listPage - 1) * listPageSize, listPage * listPageSize);

  useEffect(() => {
    if (listPage > totalPages) setListPage(totalPages);
  }, [listPage, totalPages]);

  return (
    <VStack align="stretch" spacing={4}>
      {(() => {
        const hasActiveFilters =
          userSearch.trim().length > 0 || userFilterRole !== "all" || userFilterStatus !== "all";
        return (
          <TableFilterToolbar
            hasActiveFilters={hasActiveFilters}
            onClear={() => {
              setUserSearch("");
              setUserFilterRole("all");
              setUserFilterStatus("all");
              setListPage(1);
            }}
            spacing={4}
            align="flex-end"
          >
            <InputGroup size="sm" maxW="240px">
              <InputLeftElement pointerEvents="none">
                <SearchIcon color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search users..."
                value={userSearch}
                onChange={(e) => {
                  setUserSearch(e.target.value);
                  setListPage(1);
                }}
                bg="white"
                pl={10}
              />
            </InputGroup>
        <Select size="sm" maxW="140px" value={userFilterRole} onChange={(e) => { setUserFilterRole(e.target.value); setListPage(1); }} bg="white">
          <option value="all">All Roles</option>
          {roleOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </Select>
        <Select size="sm" maxW="140px" value={userFilterStatus} onChange={(e) => { setUserFilterStatus(e.target.value); setListPage(1); }} bg="white">
          <option value="all">All Status</option>
          <option value="ACTIVE">Active</option>
          <option value="PENDING">Pending</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="DEACTIVATED">Deactivated</option>
        </Select>
          </TableFilterToolbar>
        );
      })()}
      <TableContainer>
        <Table variant="simple" size="sm">
          <Thead>
            <Tr>
              <Th>
                <TableSortHeader
                  label="Name"
                  direction={userNameSortDirection}
                  onAsc={() => setUserNameSortDirection("asc")}
                  onDesc={() => setUserNameSortDirection("desc")}
                  ascAriaLabel="Sort users by name ascending"
                  descAriaLabel="Sort users by name descending"
                />
              </Th>
              <Th>EMAIL</Th>
              <Th>ROLE</Th>
              <Th>LAST LOGIN</Th>
              <Th>STATUS</Th>
              <Th>ACTIONS</Th>
            </Tr>
          </Thead>
          <Tbody>
            {paginatedUsers.map((u) => (
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
      {totalUsers > 0 ? (
        <TablePaginationBar
          startRow={startRow}
          endRow={endRow}
          totalItems={totalUsers}
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
          borderColor="gray.200"
          bg="white"
        />
      ) : (
        <Text fontSize="sm" color="gray.500">Showing 0 user(s)</Text>
      )}
    </VStack>
  );
}

export interface TenantManagementTabProps {
  /** When true, tab is visible; used to fetch data when user switches to this tab */
  isActive?: boolean;
}

export default function TenantManagementTab({ isActive = false }: TenantManagementTabProps) {
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
  const { user } = useAuth();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");
  const tableRowHoverBg = useColorModeValue("gray.50", "gray.700");

  const tm = useTenantManagement({ user: user ?? null });
  const tenantUserAssignableRoleOptions = useMemo(
    () => TENANT_USER_ROLE_OPTIONS.filter((opt) => opt.value !== "ADMIN"),
    []
  );

  const [tenantNameSortDirection, setTenantNameSortDirection] = useState<"asc" | "desc">("asc");
  const [tenantUserNameSortDirection, setTenantUserNameSortDirection] = useState<"asc" | "desc">("asc");
  const [tenantListPage, setTenantListPage] = useState(1);
  const [tenantListPageSize, setTenantListPageSize] = useState(25);
  const [tenantUserListPage, setTenantUserListPage] = useState(1);
  const [tenantUserListPageSize, setTenantUserListPageSize] = useState(25);

  const sortedTenants = useMemo(() => {
    return [...(tm.filteredTenants ?? [])].sort((a, b) => {
      const aName = a.organization_name ?? "";
      const bName = b.organization_name ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return tenantNameSortDirection === "asc" ? nameCmp : -nameCmp;
      const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
      const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
      return timeB - timeA;
    });
  }, [tm.filteredTenants, tenantNameSortDirection]);

  const sortedTenantUsers = useMemo(() => {
    return [...(tm.filteredTenantUsers ?? [])].sort((a, b) => {
      const aName = a.username ?? "";
      const bName = b.username ?? "";
      const nameCmp = aName.localeCompare(bName, undefined, { sensitivity: "base" });
      if (nameCmp !== 0) return tenantUserNameSortDirection === "asc" ? nameCmp : -nameCmp;
      const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
      const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
      return timeB - timeA;
    });
  }, [tm.filteredTenantUsers, tenantUserNameSortDirection]);

  const totalTenants = sortedTenants.length;
  const totalTenantPages = Math.max(1, Math.ceil(totalTenants / tenantListPageSize));
  const tenantStartRow = totalTenants === 0 ? 0 : (tenantListPage - 1) * tenantListPageSize + 1;
  const tenantEndRow = Math.min(tenantListPage * tenantListPageSize, totalTenants);
  const paginatedTenants = sortedTenants.slice(
    (tenantListPage - 1) * tenantListPageSize,
    tenantListPage * tenantListPageSize
  );

  const totalTenantUsers = sortedTenantUsers.length;
  const totalTenantUserPages = Math.max(1, Math.ceil(totalTenantUsers / tenantUserListPageSize));
  const tenantUserStartRow = totalTenantUsers === 0 ? 0 : (tenantUserListPage - 1) * tenantUserListPageSize + 1;
  const tenantUserEndRow = Math.min(tenantUserListPage * tenantUserListPageSize, totalTenantUsers);
  const paginatedTenantUsers = sortedTenantUsers.slice(
    (tenantUserListPage - 1) * tenantUserListPageSize,
    tenantUserListPage * tenantUserListPageSize
  );

  useEffect(() => {
    if (tenantListPage > totalTenantPages) setTenantListPage(totalTenantPages);
  }, [tenantListPage, totalTenantPages]);

  useEffect(() => {
    if (tenantUserListPage > totalTenantUserPages) setTenantUserListPage(totalTenantUserPages);
  }, [tenantUserListPage, totalTenantUserPages]);

  const hasActiveMultiTenantFilters =
    tm.multiTenantSubView === "adopter"
      ? tm.tenantFilterStatus !== "all" ||
        tm.tenantFilterServices !== "all" ||
        tm.tenantSearch.trim().length > 0
      : tm.userFilterStatus !== "all" ||
        tm.userFilterServices !== "all" ||
        tm.userFilterRole !== "all" ||
        tm.userSearch.trim().length > 0;

  const {
    isOpen: isEditTenantConfirmOpen,
    onOpen: onEditTenantConfirmOpen,
    onClose: onEditTenantConfirmClose,
  } = useDisclosure();

  const {
    isOpen: isEditUserConfirmOpen,
    onOpen: onEditUserConfirmOpen,
    onClose: onEditUserConfirmClose,
  } = useDisclosure();

  const handleConfirmEditTenant = async () => {
    await tm.handleSaveEditTenant();
    onEditTenantConfirmClose();
  };

  const handleConfirmEditUser = async () => {
    await tm.handleSaveEditUser();
    onEditUserConfirmClose();
  };

  // When user switches to this tab or subview (Adopter vs Tenant Admin), fetch only the relevant list.
  useEffect(() => {
    if (!isActive || !user?.id) return;
    if (tm.multiTenantSubView === "adopter") {
      tm.handleFetchTenants();
    } else {
      tm.handleFetchTenantUsers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, user?.id, tm.multiTenantSubView]);

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
  const mustKeepManageServicesOpen =
    tm.manageServicesTenant?.status === "ACTIVE" &&
    tm.availableServices.length > 0 &&
    tm.manageServicesSelected.length === 0;
  const mustKeepManageUserServicesOpen =
    tm.manageUserServicesUser?.status === "ACTIVE" &&
    tm.availableServicesForUser.length > 0 &&
    tm.manageUserServicesSelected.length === 0;

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
                  <HStack
                    spacing={2}
                    px={0}
                    py={0}
                    color="gray.700"
                    cursor="default"
                    userSelect="none"
                  >
                    <FiBriefcase color="var(--chakra-colors-gray-600)" size={14} />
                    <Text fontSize="xs" fontWeight="semibold" letterSpacing="wide" textTransform="uppercase">
                      Adopter Admin
                    </Text>
                  </HStack>
                )}
                {showTenant && (
                  <HStack
                    spacing={2}
                    px={0}
                    py={0}
                    color="gray.700"
                    cursor="default"
                    userSelect="none"
                  >
                    <FiUsers color="var(--chakra-colors-gray-600)" size={14} />
                    <Text fontSize="xs" fontWeight="semibold" letterSpacing="wide" textTransform="uppercase">
                      Tenant Admin
                    </Text>
                  </HStack>
                )}
                <HStack flex={1} justify="flex-end">
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
           
            <TableFilterToolbar
              hasActiveFilters={hasActiveMultiTenantFilters}
              onClear={() => {
                tm.handleResetMultiTenantFilters();
                setTenantListPage(1);
                setTenantUserListPage(1);
              }}
              spacing={4}
              align="flex-end"
            >
              {tm.multiTenantSubView === "adopter" ? (
                <>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm"> Status</FormLabel>
                    <Select size="sm" value={tm.tenantFilterStatus} onChange={(e) => { tm.setTenantFilterStatus(e.target.value); setTenantListPage(1); }} bg="white">
                      <option value="all">All Status</option>
                      <option value="ACTIVE">Active</option>
                      <option value="PENDING">Pending</option>
                      <option value="SUSPENDED">Suspended</option>
                      <option value="DEACTIVATED">Deactivated</option>
                    </Select>
                  </FormControl>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm"> Services</FormLabel>
                    <Select size="sm" value={tm.tenantFilterServices} onChange={(e) => { tm.setTenantFilterServices(e.target.value); setTenantListPage(1); }} bg="white">
                      <option value="all">All Services</option>
                      {Array.from(new Set(tm.tenants.flatMap((t) => t.subscriptions || []))).sort().map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl maxW="240px">
                    <FormLabel fontSize="sm">Search by Tenant</FormLabel>
                    <InputGroup size="sm">
                      <InputLeftElement pointerEvents="none">
                        <SearchIcon color="gray.400" />
                      </InputLeftElement>
                      <Input
                        placeholder="Search tenant name or ID..."
                        value={tm.tenantSearch}
                        onChange={(e) => {
                          tm.setTenantSearch(e.target.value);
                          setTenantListPage(1);
                        }}
                        bg="white"
                        pl={10}
                      />
                    </InputGroup>
                  </FormControl>
                </>
              ) : (
                <>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm"> Status</FormLabel>
                    <Select size="sm" value={tm.userFilterStatus} onChange={(e) => { tm.setUserFilterStatus(e.target.value); setTenantUserListPage(1); }} bg="white">
                      <option value="all">All Status</option>
                      <option value="ACTIVE">Active</option>
                      <option value="SUSPENDED">Suspended</option>
                    </Select>
                  </FormControl>
                  <FormControl maxW="180px">
                    <FormLabel fontSize="sm"> Services</FormLabel>
                    <Select size="sm" value={tm.userFilterServices} onChange={(e) => { tm.setUserFilterServices(e.target.value); setTenantUserListPage(1); }} bg="white">
                      <option value="all">All Services</option>
                      {Array.from(new Set(tm.tenantUsers.flatMap((u) => u.subscriptions || []))).sort().map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </Select>
                  </FormControl>
                                <FormControl maxW="180px">
                                  <FormLabel fontSize="sm"> Role</FormLabel>
                                  <Select size="sm" value={tm.userFilterRole} onChange={(e) => { tm.setUserFilterRole(e.target.value); setTenantUserListPage(1); }} bg="white">
                                    <option value="all">All Roles</option>
                                    {TENANT_USER_ROLE_OPTIONS.map((opt) => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                  </Select>
                                </FormControl>
                  <FormControl maxW="240px">
                    <FormLabel fontSize="sm">Search by User</FormLabel>
                    <InputGroup size="sm">
                      <InputLeftElement pointerEvents="none">
                        <SearchIcon color="gray.400" />
                      </InputLeftElement>
                      <Input
                        size="sm"
                        placeholder="Search user name or email..."
                        value={tm.userSearch}
                        onChange={(e) => {
                          tm.setUserSearch(e.target.value);
                          setTenantUserListPage(1);
                        }}
                        bg="white"
                        pl={10}
                      />
                    </InputGroup>
                  </FormControl>
                </>
              )}
            </TableFilterToolbar>
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
                                onClick={() => tm.handleResendVerificationEmail(tm.viewTenantDetail!.tenant_id, tm.viewTenantDetail!.email)}
                                isLoading={tm.resendingVerificationTenantId === tm.viewTenantDetail.tenant_id}
                                loadingText="Resending..."
                              >
                                Resend Verification Email
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
                      <Th>
                        <TableSortHeader
                          label="Name"
                          direction={tenantNameSortDirection}
                          onAsc={() => setTenantNameSortDirection("asc")}
                          onDesc={() => setTenantNameSortDirection("desc")}
                          ascAriaLabel="Sort tenants by name ascending"
                          descAriaLabel="Sort tenants by name descending"
                        />
                      </Th>
                      <Th>TENANT ID</Th>
                      <Th>CONTACT</Th>
                      <Th>SERVICES ENABLED</Th>
                      <Th>STATUS</Th>
                      <Th>CREATED</Th>
                      <Th>ACTIONS</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                  {paginatedTenants.map((t) => (
                      <Tr
                        key={t.id}
                        cursor="pointer"
                        _hover={{ bg: tableRowHoverBg }}
                        onClick={() => tm.handleViewTenant(t)}
                      >
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
                                  onClick={() => tm.handleResendVerificationEmail(t.tenant_id, t.email)}
                                  isDisabled={tm.resendingVerificationTenantId === t.tenant_id}
                                >
                                  {tm.resendingVerificationTenantId === t.tenant_id ? "Resending..." : "Resend Verification Email"}
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
                    <Th>
                      <TableSortHeader
                        label="Name"
                        direction={tenantUserNameSortDirection}
                        onAsc={() => setTenantUserNameSortDirection("asc")}
                        onDesc={() => setTenantUserNameSortDirection("desc")}
                        ascAriaLabel="Sort tenant users by name ascending"
                        descAriaLabel="Sort tenant users by name descending"
                      />
                    </Th>
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
                  {paginatedTenantUsers.map((u) => (
                    <Tr
                      key={u.id}
                      cursor="pointer"
                      _hover={{ bg: tableRowHoverBg }}
                      onClick={() => tm.handleViewUser(u)}
                    >
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
            <TablePaginationBar
              startRow={tenantStartRow}
              endRow={tenantEndRow}
              totalItems={totalTenants}
              page={tenantListPage}
              totalPages={totalTenantPages}
              pageSize={tenantListPageSize}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              onPageSizeChange={(value) => {
                setTenantListPageSize(value);
                setTenantListPage(1);
              }}
              onFirst={() => setTenantListPage(1)}
              onPrev={() => setTenantListPage((p) => Math.max(1, p - 1))}
              onNext={() => setTenantListPage((p) => Math.min(totalTenantPages, p + 1))}
              onLast={() => setTenantListPage(totalTenantPages)}
              canPrev={tenantListPage > 1}
              canNext={tenantListPage < totalTenantPages}
              borderColor={cardBorder}
              bg={cardBg}
            />
          )}
          {!tm.tenantDetailView && tm.multiTenantSubView === "tenant" && !tm.isLoadingTenantUsers && (
            <TablePaginationBar
              startRow={tenantUserStartRow}
              endRow={tenantUserEndRow}
              totalItems={totalTenantUsers}
              page={tenantUserListPage}
              totalPages={totalTenantUserPages}
              pageSize={tenantUserListPageSize}
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              onPageSizeChange={(value) => {
                setTenantUserListPageSize(value);
                setTenantUserListPage(1);
              }}
              onFirst={() => setTenantUserListPage(1)}
              onPrev={() => setTenantUserListPage((p) => Math.max(1, p - 1))}
              onNext={() => setTenantUserListPage((p) => Math.min(totalTenantUserPages, p + 1))}
              onLast={() => setTenantUserListPage(totalTenantUserPages)}
              canPrev={tenantUserListPage > 1}
              canNext={tenantUserListPage < totalTenantUserPages}
              borderColor={cardBorder}
              bg={cardBg}
            />
          )}
        </CardBody>
      </Card>

      {/* Create New Tenant Modal */}
      <StandardModal
        isOpen={tm.isTenantModalOpen}
        onClose={tm.closeTenantModal}
        size="lg"
        title="Create New Tenant"
        contentProps={{ maxH: "90vh", display: "flex", flexDirection: "column" }}
        bodyProps={{ overflowY: "auto", flex: "1", minH: 0 }}
        footerProps={{ flexShrink: 0 }}
        footer={
          <>
            {tm.tenantModalStep === 1 && (
              <>
                <Button variant="ghost" mr={3} onClick={tm.closeTenantModal}>Cancel</Button>
                <Button colorScheme="blue" onClick={tm.handleTenantStepNext} isDisabled={!tm.tenantForm.organization_name.trim() || !tm.tenantForm.domain.trim() || !tm.tenantForm.contact_email.trim() || !tm.tenantForm.requested_subscriptions?.length}>
                  Next &rarr;
                </Button>
              </>
            )}
            {tm.tenantModalStep === 2 && (
              <>
                <Button variant="ghost" mr={3} onClick={tm.handleTenantStepBack} isDisabled={tm.isSubmittingTenant}>&larr; Back</Button>
                <Button variant="ghost" mr={3} onClick={tm.closeTenantModal} isDisabled={tm.isSubmittingTenant}>Cancel</Button>
                <Button colorScheme="blue" onClick={tm.handleRegisterTenant} isLoading={tm.isSubmittingTenant} loadingText="Sending...">
                  Register Tenant
                </Button>
              </>
            )}
          </>
        }
      >
        <Box px={0} pt={0} pb={2} flexShrink={0}>
            <HStack spacing={2}>
              <Badge colorScheme={tm.tenantModalStep === 1 ? "blue" : "green"} borderRadius="full" px={2}>1</Badge>
              <Badge colorScheme={tm.tenantModalStep === 2 ? "blue" : "gray"} borderRadius="full" px={2}>2</Badge>
            </HStack>
            <Text fontSize="sm" color="gray.600" mt={1}>Step {tm.tenantModalStep} of 2</Text>
        </Box>
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
                <FormControl isRequired isInvalid={!!tm.tenantFormErrors.contact_email}>
                  <FormLabel>Contact Email</FormLabel>
                  <Input
                    type="email"
                    placeholder="contact@organization.com"
                    value={tm.tenantForm.contact_email}
                    onChange={(e) => {
                      const value = e.target.value;
                      tm.setTenantForm((f) => ({ ...f, contact_email: value }));
                      tm.checkTenantContactEmailUnique(value);
                    }}
                    bg="white"
                  />
                  {tm.tenantFormErrors.contact_email && <FormErrorMessage>{tm.tenantFormErrors.contact_email}</FormErrorMessage>}
                </FormControl>
                <FormControl>
                  <FormLabel>Contact Phone (optional)</FormLabel>
                  <Input placeholder="+91 XXXXXXXXXX (optional)" value={tm.tenantForm.contact_phone} onChange={(e) => tm.setTenantForm((f) => ({ ...f, contact_phone: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl>
                  <FormLabel>Description (optional)</FormLabel>
                  <Input placeholder="Brief description of the tenant organization" value={tm.tenantForm.description} onChange={(e) => tm.setTenantForm((f) => ({ ...f, description: e.target.value }))} bg="white" />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel>Requested subscriptions</FormLabel>
                  {tm.isLoadingServicesForCreate ? (
                    <Box borderWidth="1px" borderRadius="md" p={4} bg="white">
                      <Spinner size="sm" mr={2} />
                      <Text as="span" fontSize="sm" color="gray.600">Loading services…</Text>
                    </Box>
                  ) : tm.availableServicesForCreate && tm.availableServicesForCreate.length > 0 ? (
                    <Box borderWidth="1px" borderRadius="md" p={3} bg="white" maxH="200px" overflowY="auto">
                      {(() => {
                        const allServiceNames = tm.availableServicesForCreate.map((svc) => svc.service_name);
                        const allSelected =
                          allServiceNames.length > 0 &&
                          allServiceNames.every((name) => tm.tenantForm.requested_subscriptions?.includes(name));
                        return (
                          <>
                            <HStack justify="space-between" mb={2}>
                              <Checkbox
                                isChecked={allSelected}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    tm.setTenantForm((f) => ({
                                      ...f,
                                      requested_subscriptions: allServiceNames.filter(Boolean) as string[],
                                    }));
                                  } else {
                                    tm.setTenantForm((f) => ({ ...f, requested_subscriptions: [] }));
                                  }
                                }}
                                colorScheme="blue"
                                size="sm"
                              >
                                <Text fontSize="sm" fontWeight="semibold">
                                  Select All
                                </Text>
                              </Checkbox>
                            </HStack>
                            <CheckboxGroup
                              value={tm.tenantForm.requested_subscriptions || []}
                              onChange={(values) =>
                                tm.setTenantForm((f) => ({ ...f, requested_subscriptions: values as string[] }))
                              }
                            >
                              <VStack align="stretch" spacing={2}>
                                {tm.availableServicesForCreate.map((svc) => (
                                  <Checkbox key={svc.id} value={svc.service_name} colorScheme="blue" size="sm">
                                    <Text fontSize="sm">{(svc.service_name ?? "").toUpperCase()}</Text>
                                  </Checkbox>
                                ))}
                              </VStack>
                            </CheckboxGroup>
                          </>
                        );
                      })()}
                    </Box>
                  ) : (
                    <Box borderWidth="1px" borderRadius="md" p={3} bg="white">
                      <Text fontSize="sm" color="gray.600" mb={2}>
                        {tm.availableServicesForCreate && tm.availableServicesForCreate.length === 0
                          ? "No services available from the server."
                          : "Could not load services."}
                      </Text>
                      <Button size="sm" colorScheme="blue" variant="outline" onClick={tm.loadServicesForCreateTenant} isLoading={tm.isLoadingServicesForCreate} loadingText="Loading...">
                        Load services
                      </Button>
                    </Box>
                  )}
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
                    A verification email needs to be sent to <strong>{tm.tenantForm.contact_email}</strong>. The tenant will remain in pending status until verified.
                  </AlertDescription>
                </Alert>
              </VStack>
            )}
      </StandardModal>

      {/* Manage Services Modal (existing tenant) */}
      <StandardModal
        isOpen={tm.isManageServicesModalOpen}
        onClose={mustKeepManageServicesOpen ? () => {} : tm.closeManageServices}
        size="lg"
        title="Manage Services"
        closeOnOverlayClick={!mustKeepManageServicesOpen}
        closeOnEsc={!mustKeepManageServicesOpen}
        hideCloseButton={mustKeepManageServicesOpen}
        footer={
          tm.availableServices.length > 0 ? (
            <>
              <Button variant="ghost" mr={3} onClick={tm.closeManageServices} isDisabled={mustKeepManageServicesOpen}>Cancel</Button>
              <Button
                colorScheme="blue"
                onClick={tm.saveManageServices}
                isDisabled={tm.manageServicesTenant?.status === "ACTIVE" && tm.manageServicesSelected.length === 0}
              >
                Done
              </Button>
            </>
          ) : undefined
        }
      >
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
                    <Text fontSize="sm" color="gray.600">
                      Check to add or uncheck to remove a service for this tenant. Changes are applied immediately.
                    </Text>
                    <HStack justify="space-between">
                      <Checkbox
                        isChecked={
                          tm.availableServices.length > 0 &&
                          tm.availableServices.every((svc) =>
                            tm.manageServicesSelected.includes(svc.service_name)
                          )
                        }
                        onChange={(e) => {
                          const checked = e.target.checked;
                          tm.availableServices.forEach((svc) => {
                            const isCurrentlySelected = tm.manageServicesSelected.includes(svc.service_name);
                            if (checked && !isCurrentlySelected) {
                              tm.handleTenantServiceCheckChange(svc.service_name, true);
                            } else if (!checked && isCurrentlySelected) {
                              tm.handleTenantServiceCheckChange(svc.service_name, false);
                            }
                          });
                        }}
                        isDisabled={tm.isSavingManageServices}
                        colorScheme="blue"
                        size="sm"
                      >
                        <Text fontSize="sm" fontWeight="semibold">
                          Select All
                        </Text>
                      </Checkbox>
                    </HStack>
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
                    <Text fontSize="sm" color="gray.500">
                      {tm.manageServicesSelected.length} service(s) selected
                    </Text>
                    {tm.manageServicesTenant?.status === "ACTIVE" && tm.manageServicesSelected.length === 0 && (
                      <Alert status="error" borderRadius="md" mt={2}>
                        <AlertIcon />
                        <AlertDescription>
                          Active tenants must have at least one service assigned. Select at least one service before saving.
                        </AlertDescription>
                      </Alert>
                    )}
                  </VStack>
                )}
          </>
        )}
      </StandardModal>

      {/* Manage User Services Modal */}
      <StandardModal
        isOpen={tm.isManageUserServicesModalOpen}
        onClose={mustKeepManageUserServicesOpen ? () => {} : tm.closeManageUserServices}
        size="lg"
        title="Manage User Services"
        closeOnOverlayClick={!mustKeepManageUserServicesOpen}
        closeOnEsc={!mustKeepManageUserServicesOpen}
        hideCloseButton={mustKeepManageUserServicesOpen}
        footer={
          tm.availableServicesForUser.length > 0 ? (
            <>
              <Button
                variant="ghost"
                mr={3}
                onClick={tm.closeManageUserServices}
                isDisabled={mustKeepManageUserServicesOpen}
              >
                Cancel
              </Button>
              <Button
                colorScheme="blue"
                onClick={tm.saveManageUserServices}
                isDisabled={tm.manageUserServicesUser?.status === "ACTIVE" && tm.manageUserServicesSelected.length === 0}
              >
                Done
              </Button>
            </>
          ) : undefined
        }
      >
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
                    <Text fontSize="sm" color="gray.600">
                      Check to add or uncheck to remove a service for this user. Changes are applied immediately.
                    </Text>
                    <HStack justify="space-between">
                      <Checkbox
                        isChecked={
                          tm.availableServicesForUser.length > 0 &&
                          tm.availableServicesForUser.every((svc) =>
                            tm.manageUserServicesSelected.includes(svc.service_name)
                          )
                        }
                        onChange={(e) => {
                          const checked = e.target.checked;
                          tm.availableServicesForUser.forEach((svc) => {
                            const isCurrentlySelected = tm.manageUserServicesSelected.includes(svc.service_name);
                            if (checked && !isCurrentlySelected) {
                              tm.handleUserServiceCheckChange(svc.service_name, true);
                            } else if (!checked && isCurrentlySelected) {
                              tm.handleUserServiceCheckChange(svc.service_name, false);
                            }
                          });
                        }}
                        isDisabled={tm.isSavingManageUserServices}
                        colorScheme="blue"
                        size="sm"
                      >
                        <Text fontSize="sm" fontWeight="semibold">
                          Select All
                        </Text>
                      </Checkbox>
                    </HStack>
                    <Box borderWidth="1px" borderRadius="md" p={3} bg="white" maxH="280px" overflowY="auto" overflowX="hidden">
                      <VStack align="stretch" spacing={2}>
                        {tm.availableServicesForUser.map((svc) => (
                          <Checkbox
                            key={svc.id}
                            isChecked={tm.manageUserServicesSelected.includes(svc.service_name)}
                            onChange={(e) => tm.handleUserServiceCheckChange(svc.service_name, e.target.checked)}
                            isDisabled={tm.isSavingManageUserServices}
                            colorScheme="blue"
                            size="sm"
                          >
                            <Text fontSize="sm" fontWeight="medium" whiteSpace="normal" wordBreak="break-word">
                              {(svc.service_name ?? "").toUpperCase()}
                            </Text>
                          </Checkbox>
                        ))}
                      </VStack>
                    </Box>
                    <Text fontSize="sm" color="gray.500">
                      {tm.manageUserServicesSelected.length} service(s) selected
                    </Text>
                    {tm.manageUserServicesUser?.status === "ACTIVE" && tm.manageUserServicesSelected.length === 0 && (
                      <Alert status="error" borderRadius="md" mt={2}>
                        <AlertIcon />
                        <AlertDescription>
                          Active users must have at least one service assigned. Select at least one service before saving.
                        </AlertDescription>
                      </Alert>
                    )}
                  </VStack>
                )}
          </>
        )}
      </StandardModal>

      {/* Add New User Modal */}
      <StandardModal
        isOpen={tm.isUserModalOpen}
        onClose={tm.closeUserModal}
        size="md"
        title="Add New User"
        footer={
          <>
            <Button variant="ghost" mr={3} onClick={tm.closeUserModal} isDisabled={tm.isSubmittingUser}>Cancel</Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleRegisterUser}
              isLoading={tm.isSubmittingUser}
              loadingText="Adding..."
              isDisabled={
                !tm.userForm.tenant_id ||
                !tm.userForm.full_name?.trim() ||
                !tm.userForm.email.trim() ||
                !tm.userForm.username.trim() ||
                tm.userForm.username.trim().length < 3 ||
                (() => {
                  const selectedTenant = tm.tenants.find((t) => t.tenant_id === tm.userForm.tenant_id);
                  const tenantServices = selectedTenant?.subscriptions ?? [];
                  return tenantServices.length > 0 && (tm.userForm.services?.length ?? 0) === 0;
                })()
              }
            >
              + Add User
            </Button>
          </>
        }
      >
        <VStack spacing={4} align="stretch">
              <FormControl isRequired>
                <FormLabel>Tenant</FormLabel>
                <Input
                  value={tm.userForm.tenant_id ? (() => {
                    const t = tm.tenants.find((x) => x.tenant_id === tm.userForm.tenant_id);
                    return t ? `${t.organization_name || t.tenant_id} (${t.tenant_id})` : tm.userForm.tenant_id;
                  })() : "Select a tenant first"}
                  isReadOnly
                  variant="filled"
                  bg="gray.50"
                  _readOnly={{ cursor: "default" }}
                />
           
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Full Name</FormLabel>
                <Input placeholder="Enter user's full name" value={tm.userForm.full_name} onChange={(e) => tm.setUserForm((f) => ({ ...f, full_name: e.target.value }))} bg="white" />
              </FormControl>
              <FormControl isRequired isInvalid={!!tm.userFormErrors?.email}>
                <FormLabel>Email Address</FormLabel>
                <Input
                  type="email"
                  placeholder="user@organization.com"
                  value={tm.userForm.email}
                  onChange={(e) => {
                    const value = e.target.value;
                    tm.setUserForm((f) => ({ ...f, email: value }));
                    tm.checkUserEmailUnique(value);
                  }}
                  bg="white"
                />
                {tm.userFormErrors?.email && <FormErrorMessage>{tm.userFormErrors.email}</FormErrorMessage>}
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Username</FormLabel>
                <Input placeholder="Username (min 3 characters)" value={tm.userForm.username} onChange={(e) => tm.setUserForm((f) => ({ ...f, username: e.target.value }))} bg="white" />
              </FormControl>
              <FormControl>
                <FormLabel>Role</FormLabel>
                <Select value={tm.userForm.role || "USER"} onChange={(e) => tm.setUserForm((f) => ({ ...f, role: e.target.value }))} bg="white">
                  {tenantUserAssignableRoleOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
              </FormControl>
              <FormControl
                isInvalid={(() => {
                  const selectedTenant = tm.tenants.find((t) => t.tenant_id === tm.userForm.tenant_id);
                  const tenantServices = selectedTenant?.subscriptions ?? [];
                  return tenantServices.length > 0 && (tm.userForm.services?.length ?? 0) === 0;
                })()}
              >
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
                  const allSelected =
                    tenantServices.length > 0 &&
                    tenantServices.every((svc) => tm.userForm.services.includes(svc));
                  const noServicesSelected = (tm.userForm.services?.length ?? 0) === 0;
                  return (
                    <>
                      <HStack justify="space-between" mb={2}>
                        <Checkbox
                          isChecked={allSelected}
                          onChange={(e) => {
                            if (e.target.checked) {
                              tm.setUserForm((f) => ({ ...f, services: [...tenantServices] }));
                            } else {
                              tm.setUserForm((f) => ({ ...f, services: [] }));
                            }
                          }}
                          colorScheme="blue"
                          size="sm"
                        >
                          <Text fontSize="sm" fontWeight="semibold">
                            Select All
                          </Text>
                        </Checkbox>
                      </HStack>
                      <CheckboxGroup
                        value={tm.userForm.services}
                        onChange={(values) => tm.setUserForm((f) => ({ ...f, services: values as string[] }))}
                      >
                        <SimpleGrid columns={2} spacing={3} minChildWidth="140px">
                          {tenantServices.map((svc) => (
                            <Checkbox key={svc} value={svc} colorScheme="blue" size="sm" whiteSpace="normal">
                              <Text fontSize="sm" fontWeight="medium" whiteSpace="normal" wordBreak="break-word">
                                {String(svc).toUpperCase()}
                              </Text>
                            </Checkbox>
                          ))}
                        </SimpleGrid>
                      </CheckboxGroup>
                      {noServicesSelected && (
                        <FormErrorMessage mt={2}>
                          At least one service must be assigned to the new user.
                        </FormErrorMessage>
                      )}
                    </>
                  );
                })()}
              </FormControl>
        </VStack>
      </StandardModal>

      {/* View Tenant Details Modal */}
      <StandardModal
        isOpen={tm.isViewTenantModalOpen}
        onClose={tm.closeViewTenantModal}
        size="lg"
        title="Tenant Details"
        footer={<Button onClick={tm.closeViewTenantModal}>Close</Button>}
      >
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
      </StandardModal>

      {/* View User Details Modal */}
      <StandardModal
        isOpen={tm.isViewUserModalOpen}
        onClose={tm.closeViewUserModal}
        size="md"
        title="User Details"
        footer={<Button onClick={tm.closeViewUserModal}>Close</Button>}
      >
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
      </StandardModal>

      {/* Edit Tenant Modal */}
      <StandardModal
        isOpen={tm.isEditTenantModalOpen}
        onClose={tm.closeEditTenantModal}
        size="lg"
        title="Edit Tenant"
        footer={
          <>
            <Button variant="ghost" mr={3} onClick={tm.closeEditTenantModal} isDisabled={tm.isSubmittingEditTenant}>Cancel</Button>
            <Button
              colorScheme="blue"
              onClick={onEditTenantConfirmOpen}
              isLoading={tm.isSubmittingEditTenant}
              isDisabled={!tm.editTenantForm.organization_name?.trim() || !tm.editTenantForm.contact_email?.trim() || !tm.editTenantForm.domain?.trim()}
            >
              Save Changes
            </Button>
          </>
        }
      >
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
                  <Input
                    type="email"
                    value={tm.editTenantForm.contact_email ?? ""}
                    isReadOnly
                    variant="filled"
                    bg="gray.50"
                    _readOnly={{ cursor: "default" }}
                  />
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
      </StandardModal>

      {/* Edit User Modal */}
      <StandardModal
        isOpen={tm.isEditUserModalOpen}
        onClose={tm.closeEditUserModal}
        size="md"
        title="Edit User"
        footer={
          <>
            <Button variant="ghost" mr={3} onClick={tm.closeEditUserModal} isDisabled={tm.isSubmittingEditUser}>Cancel</Button>
            <Button
              colorScheme="blue"
              onClick={onEditUserConfirmOpen}
              isLoading={tm.isSubmittingEditUser}
              isDisabled={!tm.editUserForm.username?.trim() || tm.editUserForm.username.trim().length < 3}
            >
              Save Changes
            </Button>
          </>
        }
      >
        {tm.editUserRow && (
          <VStack align="stretch" spacing={4}>
            <FormControl>
              <FormLabel>Tenant ID</FormLabel>
              <Input
                value={tm.editUserForm.tenant_id}
                isReadOnly
              />
            </FormControl>
            <FormControl>
              <FormLabel>User ID</FormLabel>
              <Input
                value={String(tm.editUserForm.user_id)}
                isReadOnly
              />
            </FormControl>
            <FormControl isRequired>
              <FormLabel>Username</FormLabel>
              <Input
                value={tm.editUserForm.username ?? ""}
                onChange={(e) => tm.setEditUserForm((f) => ({ ...f, username: e.target.value }))}
                placeholder="Username"
                minLength={3}
              />
            </FormControl>
            <FormControl>
              <FormLabel>Email</FormLabel>
              <Input
                type="email"
                value={tm.editUserForm.email ?? ""}
                isReadOnly
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                Email cannot be changed for now.
              </Text>
            </FormControl>
            <FormControl>
              <FormLabel>Role (optional)</FormLabel>
              <Select
                value={(tm.editUserForm.role ?? "USER") === "ADMIN" ? "USER" : (tm.editUserForm.role ?? "USER")}
                onChange={(e) => tm.setEditUserForm((f) => ({ ...f, role: e.target.value }))}
              >
                {tenantUserAssignableRoleOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </Select>
            </FormControl>
          </VStack>
        )}
      </StandardModal>

      {/* Delete User Confirmation */}
      <ConfirmDialog
        isOpen={tm.isDeleteUserDialogOpen}
        onClose={tm.closeDeleteUserDialog}
        onConfirm={tm.handleConfirmDeleteUser}
        title="Delete user?"
        body={
          tm.deleteUserTarget && (
            <>
              This will permanently delete the user{" "}
              {tm.deleteUserTarget.username
                ? `"${tm.deleteUserTarget.username}"`
                : `(ID ${tm.deleteUserTarget.user_id})`}{" "}
              from the tenant. This action cannot be undone.
            </>
          )
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        confirmColorScheme="red"
        isConfirmLoading={tm.isDeletingUser}
        leastDestructiveRef={cancelRef}
      />

      {/* Status Update Confirmation */}
      <ConfirmDialog
        isOpen={tm.isStatusDialogOpen}
        onClose={tm.closeStatusDialog}
        onConfirm={tm.handleConfirmStatusUpdate}
        title={`Update status to ${tm.statusUpdateNewStatus}?`}
        body={
          tm.statusUpdateTarget?.type === "tenant" ? (
            <>
              Tenant <strong>{tm.statusUpdateTarget.tenant_id}</strong> will be
              set to <strong>{tm.statusUpdateNewStatus}</strong>. Current
              status: {tm.statusUpdateTarget.currentStatus}.
            </>
          ) : tm.statusUpdateTarget?.type === "user" ? (
            <>
              User ID <strong>{tm.statusUpdateTarget.user_id}</strong> (tenant{" "}
              {tm.statusUpdateTarget.tenant_id}) will be set to{" "}
              <strong>{tm.statusUpdateNewStatus}</strong>. Current status:{" "}
              {tm.statusUpdateTarget.currentStatus}.
            </>
          ) : null
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="orange"
        isConfirmLoading={tm.isSubmittingStatus}
        leastDestructiveRef={cancelRef}
      />

      {/* Edit Tenant Confirmation */}
      <ConfirmDialog
        isOpen={isEditTenantConfirmOpen}
        onClose={onEditTenantConfirmClose}
        onConfirm={handleConfirmEditTenant}
        title="Save tenant changes?"
        body={
          <>
            Are you sure you want to update the details for tenant{" "}
            <strong>{tm.editTenantForm.tenant_id}</strong>?
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="blue"
        isConfirmLoading={tm.isSubmittingEditTenant}
        leastDestructiveRef={cancelRef}
      />

      {/* Edit User Confirmation */}
      <ConfirmDialog
        isOpen={isEditUserConfirmOpen}
        onClose={onEditUserConfirmClose}
        onConfirm={handleConfirmEditUser}
        title="Save user changes?"
        body={
          <>
            Are you sure you want to update the details for user{" "}
            <strong>{tm.editUserForm.username || tm.editUserForm.email}</strong>?
          </>
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        confirmColorScheme="blue"
        isConfirmLoading={tm.isSubmittingEditUser}
        leastDestructiveRef={cancelRef}
      />
    </>
  );
}
