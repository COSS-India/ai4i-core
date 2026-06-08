import { useEffect, useMemo } from "react";
import { Badge } from "@chakra-ui/react";
import { useAuth } from "../../../hooks/useAuth";
import { type AdminTableColumn } from "../../common/AdminDataTable";
import TenantUserRoleBadges from "../../common/TenantUserRoleBadges";
import TenantRowActions from "../tenant/TenantRowActions";
import UserRowActions from "../tenant/UserRowActions";
import { dash, fmtDate } from "../tenant/utils";
import {
  formatTenantStatusLabel,
  formatTenantUserStatusLabel,
  getTenantStatusColorScheme,
  resolveTenantUserDisplayStatus,
} from "../../../config/constants";
import type { TenantUserView, TenantView } from "../../../types/tenant";
import { useTenantManagement } from "./useTenantManagement";

export interface UseTenantManagementTabOptions {
  isActive?: boolean;
}

export function useTenantManagementTab({ isActive = false }: UseTenantManagementTabOptions = {}) {
  const { user } = useAuth();
  const tm = useTenantManagement({ user });

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const userListTenantStatus = tm.activeUserListTenant?.status ?? null;

  const resolveUserDisplayStatus = (u: TenantUserView) =>
    resolveTenantUserDisplayStatus(u, userListTenantStatus);

  useEffect(() => {
    if (!isActive || !user) return;
    if (isAdmin) {
      void tm.handleFetchTenants();
    } else {
      void tm.handleFetchTenantUsers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, user, isAdmin]);

  useEffect(() => {
    if (!tm.tenantDetailView) return;
    void tm.handleFetchTenantUsers(tm.tenantDetailView.tenant_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm.tenantDetailView?.tenant_id]);

  const tenantColumns = useMemo((): AdminTableColumn<TenantView>[] => {
    return [
      { id: "organisation", header: "Organisation", cell: (t) => t.organisation },
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
        header: "",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (t) => <TenantRowActions tenant={t} tm={tm} />,
      },
    ];
  }, [tm]);

  const userColumns = useMemo((): AdminTableColumn<TenantUserView>[] => {
    return [
      { id: "username", header: "Username", cell: (u) => u.username ?? dash(u.email) },
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
          <Badge colorScheme={getTenantStatusColorScheme(resolveUserDisplayStatus(u))}>
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
        cell: (u) => (
          <UserRowActions user={u} tm={tm} userListTenantStatus={userListTenantStatus} />
        ),
      },
    ];
  }, [tm, userListTenantStatus]);

  return {
    tm,
    isAdmin,
    tenantColumns,
    userColumns,
    userListTenantStatus,
    resolveUserDisplayStatus,
  };
}

export type UseTenantManagementTabReturn = ReturnType<typeof useTenantManagementTab>;
