import { useMemo } from "react";
import { Badge, Text } from "@chakra-ui/react";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
  type DataTableSortState,
} from "../common/table";
import TenantUserRoleBadges from "../common/TenantUserRoleBadges";
import { InstitutionUserRowActions } from "./InstitutionRowActions";
import {
  INSTITUTION,
  TENANT_USER_STATUS_LIST,
  formatTenantUserStatusLabel,
  getTenantStatusColorScheme,
  type TenantUserStatusValue,
} from "../../config/constants";
import { dash, fmtDate } from "../../utils/valueFormatters";
import type { TenantUserView } from "../../types/tenant";
import {
  getRegistrationMethodOption,
  REGISTRATION_METHOD_OPTIONS,
  resolveRegistrationMethod,
} from "../../utils/registrationMethod";
import { useTenantManagement } from "./hooks/useTenantManagement";

type TenantManagement = ReturnType<typeof useTenantManagement>;

function RegistrationMethodBadge({ user }: Readonly<{ user: TenantUserView }>) {
  const option = getRegistrationMethodOption(resolveRegistrationMethod(user));
  if (!option) return <>{dash(null)}</>;
  return (
    <Badge colorScheme={option.colorScheme} textTransform="none">
      {option.label}
    </Badge>
  );
}

const rolesColumn: DataTableColumn<TenantUserView> = {
  id: "roles",
  header: "Roles",
  cell: (u) => <TenantUserRoleBadges roles={u.roles} />,
};

const registrationColumn: DataTableColumn<TenantUserView> = {
  id: "registration_method",
  header: "Registration Method",
  cell: (u) => <RegistrationMethodBadge user={u} />,
};

type InstitutionUsersTableProps = Readonly<{
  tm: TenantManagement;
  sortedTenantUsers: TenantUserView[];
  userSort: {
    sort: DataTableSortState;
    onSortChange: (next: DataTableSortState) => void;
  };
  resolveUserDisplayStatus: (user: TenantUserView) => TenantUserStatusValue;
}>;

export function InstitutionUsersTable({
  tm,
  sortedTenantUsers,
  userSort,
  resolveUserDisplayStatus,
}: InstitutionUsersTableProps) {
  // Registration Method only applies to the Default Institution: every user in
  // other institutions is admin-created.
  const showRegistrationMethod = tm.isDefaultTenantUsersView;

  const userColumns = useMemo((): DataTableColumn<TenantUserView>[] => {
    return [
      {
        id: "username",
        header: "Username",
        sortable: true,
        sortAccessor: (u) => u.username ?? u.email ?? "",
        cell: (u) => (
          <Text fontWeight="medium" fontSize="sm">
            {u.username ?? dash(u.email)}
          </Text>
        ),
      },
      {
        id: "email",
        header: "Email",
        sortable: true,
        sortAccessor: (u) => u.email ?? "",
        cell: (u) => dash(u.email),
      },
      {
        id: "full_name",
        header: "Full Name",
        sortable: true,
        sortAccessor: (u) => u.full_name ?? "",
        cell: (u) => dash(u.full_name),
      },
      rolesColumn,
      ...(showRegistrationMethod ? [registrationColumn] : []),
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
        sortable: true,
        sortAccessor: (u) => {
          const created = (u as { created_at?: string }).created_at;
          return created ? new Date(created).getTime() : 0;
        },
        cell: (u) => fmtDate((u as { created_at?: string }).created_at),
      },
      {
        id: "actions",
        header: "",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (u) => (
          <InstitutionUserRowActions
            tm={tm}
            user={u}
            resolveUserDisplayStatus={resolveUserDisplayStatus}
          />
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm, showRegistrationMethod]);

  return (
      <DataTable
        layout="admin"
        key={tm.tenantDetailView?.tenant_id ?? "tenant-users"}
        items={sortedTenantUsers}
        columns={userColumns}
        getRowKey={(u) => u.user_id}
        sort={userSort.sort}
        onSortChange={userSort.onSortChange}
        onRowClick={tm.handleViewUser}
        isLoading={tm.isLoadingTenantUsers}
        emptyMessage={`No users in this ${INSTITUTION.toLowerCase()}.`}
        noResultsMessage="No users match the current filters."
        unfilteredCount={tm.tenantUsers.length}
        hasActiveFilters={
          tm.userFilterStatus !== "all" ||
          tm.userFilterRole !== "all" ||
          tm.userFilterRegistration !== "all" ||
          tm.userSearch.trim() !== ""
        }
        onClearFilters={tm.handleResetUserFilters}
        paginate="client"
        paginationPosition="bottom"
        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        search={{
          value: tm.userSearch,
          onChange: tm.setUserSearch,
          placeholder: "Search by username, email, or full name",
          fields: ["username", "email", "full_name"],
        }}
        filterDefs={[
          {
            id: "status",
            label: "Status",
            type: "select",
            param: "status",
            value: tm.userFilterStatus,
            onChange: tm.setUserFilterStatus,
            width: { base: "full", sm: "200px" },
            options: [
              { label: "All statuses", value: "all" },
              ...TENANT_USER_STATUS_LIST.map((s) => ({
                label: formatTenantUserStatusLabel(s),
                value: s,
              })),
            ],
          },
          {
            id: "role",
            label: "Role",
            type: "select",
            param: "role",
            value: tm.userFilterRole,
            onChange: tm.setUserFilterRole,
            width: { base: "full", sm: "200px" },
            options: [
              { label: "All roles", value: "all" },
              ...tm.tenantUserRoleFilterOptions.map((opt) => ({
                label: opt.label,
                value: opt.value,
              })),
            ],
          },
          ...(showRegistrationMethod
            ? [
                {
                  id: "registration_method",
                  label: "Registration Method",
                  type: "select" as const,
                  param: "registration_method",
                  value: tm.userFilterRegistration,
                  onChange: tm.setUserFilterRegistration,
                  width: { base: "full", sm: "200px" },
                  options: [
                    { label: "All", value: "all" },
                    ...REGISTRATION_METHOD_OPTIONS.map((opt) => ({
                      label: opt.label,
                      value: opt.value,
                    })),
                  ],
                },
              ]
            : []),
        ]}
      />
    );
}
