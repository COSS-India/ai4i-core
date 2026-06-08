// Tenant Management tab — backed by auth-service tenant endpoints.

import { Box } from "@chakra-ui/react";
import { useTenantManagementTab } from "./hooks/useTenantManagementTab";
import AddUserModal from "./tenant/modals/AddUserModal";
import CreateTenantModal from "./tenant/modals/CreateTenantModal";
import DeleteUserDialog from "./tenant/modals/DeleteUserDialog";
import EditTenantModal from "./tenant/modals/EditTenantModal";
import EditUserModal from "./tenant/modals/EditUserModal";
import TenantStatusConfirmDialog from "./tenant/modals/TenantStatusConfirmDialog";
import ViewUserModal from "./tenant/modals/ViewUserModal";
import TenantAdopterView from "./tenant/TenantAdopterView";
import TenantDetailView from "./tenant/TenantDetailView";
import TenantUsersCard from "./tenant/TenantUsersCard";

export interface TenantManagementTabProps {
  isActive?: boolean;
}

export default function TenantManagementTab({ isActive = false }: TenantManagementTabProps) {
  const tab = useTenantManagementTab({ isActive });
  const { tm, isAdmin, userListTenantStatus } = tab;

  return (
    <Box>
      {isAdmin && !tm.tenantDetailView && <TenantAdopterView {...tab} />}
      {!isAdmin && !tm.tenantDetailView && <TenantUsersCard {...tab} />}
      {tm.tenantDetailView && <TenantDetailView {...tab} />}

      <CreateTenantModal tm={tm} isAdmin={isAdmin} />
      <EditTenantModal tm={tm} isAdmin={isAdmin} />
      <AddUserModal tm={tm} isAdmin={isAdmin} />
      <EditUserModal tm={tm} isAdmin={isAdmin} />
      <ViewUserModal tm={tm} isAdmin={isAdmin} userListTenantStatus={userListTenantStatus} />
      <TenantStatusConfirmDialog tm={tm} isAdmin={isAdmin} />
      <DeleteUserDialog tm={tm} isAdmin={isAdmin} />
    </Box>
  );
}
