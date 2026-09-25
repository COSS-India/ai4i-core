import {
  FormControl,
  FormErrorMessage,
  Input,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import {
  INSTITUTION,
  INSTITUTION_ARTICLE,
} from "../../config/constants";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import TenantUserRoleBadges from "../common/TenantUserRoleBadges";
import { dash } from "../../utils/valueFormatters";
import { useAuth } from "../../hooks/useAuth";
import { isPlatformAdminUser } from "../../utils/rbac";
import {
  DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
  formatPlatformRoleLabel,
  isDefaultTenant,
} from "../../utils/defaultTenant";
import { TENANT_USER_ROLE_OPTIONS } from "../profile/types";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";

export type InstitutionUserFormMode = "create" | "edit" | "view";

type InstitutionUserFormProps = {
  mode: InstitutionUserFormMode;
  tm: ReturnType<typeof useTenantManagement>;
};

function ReadOnlyValue({ children }: { children: React.ReactNode }) {
  return (
    <Text fontSize="md" color="ink.700" py={1}>
      {children}
    </Text>
  );
}

/**
 * Shared Institution User fields.
 * Create adds the institution picker. Edit adds username.
 * View renders the same fields read-only. User ID and status stay outside.
 */
export default function InstitutionUserForm({ mode, tm }: InstitutionUserFormProps) {
  const { user } = useAuth();
  const isAdmin = isPlatformAdminUser(user?.roles);
  const isView = mode === "view";
  const isCreate = mode === "create";
  const viewUser = tm.viewUserDetail;

  const createRoleOptions = useMemo(() => {
    const tenantId =
      tm.lockedUserFormTenantId ?? tm.userForm.tenant_id?.trim() ?? "";
    const selected = tm.tenants.find((t) => t.tenant_id === tenantId);
    if (selected && isDefaultTenant(selected)) {
      return DEFAULT_ORG_USER_FORM_ROLE_OPTIONS;
    }
    return TENANT_USER_ROLE_OPTIONS;
  }, [tm.lockedUserFormTenantId, tm.userForm.tenant_id, tm.tenants]);

  const editRoleOptions = useMemo((): ReadonlyArray<{
    value: string;
    label: string;
  }> => {
    const tenant = tm.tenants.find(
      (t) => t.tenant_id === tm.editUserForm.tenant_id,
    );
    const isDefaultOrg =
      (tenant && isDefaultTenant(tenant)) ||
      (tm.tenantDetailView && isDefaultTenant(tm.tenantDetailView)) ||
      tm.isDefaultTenantUsersView;
    if (!isDefaultOrg) return TENANT_USER_ROLE_OPTIONS;

    const current = (tm.editUserForm.role || "").trim().toUpperCase();
    if (
      current &&
      !DEFAULT_ORG_USER_FORM_ROLE_OPTIONS.some((o) => o.value === current)
    ) {
      return [
        { value: current, label: formatPlatformRoleLabel(current) },
        ...DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
      ];
    }
    return DEFAULT_ORG_USER_FORM_ROLE_OPTIONS;
  }, [
    tm.tenants,
    tm.editUserForm.tenant_id,
    tm.editUserForm.role,
    tm.tenantDetailView,
    tm.isDefaultTenantUsersView,
  ]);

  return (
    <VStack spacing={4} align="stretch">
      {isCreate && isAdmin && tm.lockedUserFormTenantId && (
        <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.tenant_id)}>
          <FieldLabel>{INSTITUTION}</FieldLabel>
          <Input
            value={tm.getLockedUserFormTenantLabel()}
            isReadOnly
            bg="ink.50"
            _dark={{ bg: "whiteAlpha.100" }}
            cursor="not-allowed"
          />
          <FormErrorMessage>{tm.userFormErrors.tenant_id}</FormErrorMessage>
          <FieldHint>{FIELD_HINTS.tenantUser.tenant.helper}</FieldHint>
        </FormControl>
      )}
      {isCreate && isAdmin && !tm.lockedUserFormTenantId && (
        <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.tenant_id)}>
          <FieldLabel>{INSTITUTION}</FieldLabel>
          <Select
            value={tm.userForm.tenant_id}
            onChange={(e) => tm.setUserFormTenantId(e.target.value)}
          >
            <option value="">
              Select {INSTITUTION_ARTICLE} {INSTITUTION.toLowerCase()}…
            </option>
            {tm.tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.organisation}
              </option>
            ))}
          </Select>
          <FormErrorMessage>{tm.userFormErrors.tenant_id}</FormErrorMessage>
        </FormControl>
      )}

      {!isCreate && (
        <FormControl
          isRequired={mode === "edit"}
          isInvalid={mode === "edit" && Boolean(tm.editUserFormErrors.username)}
        >
          <FieldLabel variant={isView ? "inline" : undefined}>Username</FieldLabel>
          {isView ? (
            <ReadOnlyValue>{dash(viewUser?.username)}</ReadOnlyValue>
          ) : (
            <>
              <Input
                value={tm.editUserForm.username ?? ""}
                onChange={(e) => tm.handleEditUserUsernameChange(e.target.value)}
                maxLength={100}
              />
              <FormErrorMessage>{tm.editUserFormErrors.username}</FormErrorMessage>
              <FieldHint show={!tm.editUserFormErrors.username}>
                {FIELD_HINTS.tenantUser.username.helper}
              </FieldHint>
            </>
          )}
        </FormControl>
      )}

      <FormControl
        isRequired={isCreate}
        isInvalid={isCreate && Boolean(tm.userFormErrors.email)}
      >
        <FieldLabel variant={isView ? "inline" : undefined}>Email</FieldLabel>
        {isCreate ? (
          <>
            <Input
              type="email"
              value={tm.userForm.email}
              onChange={(e) => tm.handleUserEmailChange(e.target.value)}
              onBlur={tm.handleUserEmailBlur}
              placeholder={FIELD_HINTS.tenantUser.email.placeholder}
            />
            <FormErrorMessage>{tm.userFormErrors.email}</FormErrorMessage>
            <FieldHint
              show={!tm.userFormErrors.email}
              tone={tm.userEmailStatus === "available" ? "success" : "muted"}
            >
              {tm.userEmailStatus === "checking"
                ? FIELD_HINTS.tenant.emailChecking
                : tm.userEmailStatus === "available"
                  ? FIELD_HINTS.tenant.emailAvailable
                  : FIELD_HINTS.tenantUser.email.helper}
            </FieldHint>
          </>
        ) : (
          <>
            <ReadOnlyValue>
              {dash(isView ? viewUser?.email : tm.editUserRow?.email)}
            </ReadOnlyValue>
            {mode === "edit" ? (
              <FieldHint>{FIELD_HINTS.tenantUser.emailLocked}</FieldHint>
            ) : null}
          </>
        )}
      </FormControl>

      <FormControl
        isRequired={isCreate}
        isInvalid={
          isCreate
            ? Boolean(tm.userFormErrors.full_name)
            : mode === "edit" && Boolean(tm.editUserFormErrors.full_name)
        }
      >
        <FieldLabel variant={isView ? "inline" : undefined}>Full Name</FieldLabel>
        {isView ? (
          <ReadOnlyValue>{dash(viewUser?.full_name)}</ReadOnlyValue>
        ) : isCreate ? (
          <>
            <Input
              value={tm.userForm.full_name}
              onChange={(e) => tm.handleUserFullNameChange(e.target.value)}
              onBlur={(e) => tm.handleUserFullNameBlur(e.target.value)}
              placeholder={FIELD_HINTS.tenantUser.fullName.placeholder}
            />
            <FormErrorMessage>{tm.userFormErrors.full_name}</FormErrorMessage>
            <FieldHint show={!tm.userFormErrors.full_name}>
              {FIELD_HINTS.tenantUser.fullName.helper}
            </FieldHint>
          </>
        ) : (
          <>
            <Input
              value={tm.editUserForm.full_name ?? ""}
              onChange={(e) => tm.handleEditUserFullNameChange(e.target.value)}
            />
            <FormErrorMessage>{tm.editUserFormErrors.full_name}</FormErrorMessage>
            <FieldHint show={!tm.editUserFormErrors.full_name}>
              {FIELD_HINTS.tenantUser.fullName.helper}
            </FieldHint>
          </>
        )}
      </FormControl>

      <FormControl isRequired={isCreate}>
        <FieldLabel variant={isView ? "inline" : undefined} required={mode === "edit"}>
          {isView ? "Roles" : "Role"}
        </FieldLabel>
        {isView && viewUser ? (
          <TenantUserRoleBadges
            role={viewUser.role}
            roles={viewUser.roles}
            badgeFontSize="sm"
          />
        ) : isCreate ? (
          <>
            <Select
              value={tm.userForm.role}
              onChange={(e) =>
                tm.setUserForm({
                  ...tm.userForm,
                  role: e.target.value as typeof tm.userForm.role,
                })
              }
            >
              {createRoleOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
          </>
        ) : (
          <>
            <Select
              value={tm.editUserForm.role}
              isDisabled={!tm.editUserRolesLoaded || tm.isEditUserOnlyAdmin}
              onChange={(e) =>
                tm.setEditUserForm({
                  ...tm.editUserForm,
                  role: e.target.value as typeof tm.editUserForm.role,
                })
              }
            >
              {editRoleOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            {!tm.editUserRolesLoaded && (
              <FieldHint>{FIELD_HINTS.tenantUser.rolesLoadFailed}</FieldHint>
            )}
            {tm.isEditUserOnlyAdmin && (
              <FieldHint>{FIELD_HINTS.tenantUser.onlyAdminLocked}</FieldHint>
            )}
            {!tm.isEditUserOnlyAdmin && tm.editUserRolesLoaded && (
              <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
            )}
          </>
        )}
      </FormControl>

      <FormControl
        isInvalid={
          isCreate
            ? Boolean(tm.userFormErrors.phone_number)
            : mode === "edit" && Boolean(tm.editUserFormErrors.phone_number)
        }
      >
        <FieldLabel variant={isView ? "inline" : undefined}>Phone Number</FieldLabel>
        {isView ? (
          <ReadOnlyValue>{dash(viewUser?.phone_number)}</ReadOnlyValue>
        ) : isCreate ? (
          <>
            <Input
              value={tm.userForm.phone_number}
              onChange={(e) => tm.handleUserPhoneChange(e.target.value)}
              placeholder={FIELD_HINTS.tenantUser.phone.placeholder}
            />
            <FormErrorMessage>{tm.userFormErrors.phone_number}</FormErrorMessage>
            <FieldHint show={!tm.userFormErrors.phone_number}>
              {FIELD_HINTS.tenantUser.phone.helper}
            </FieldHint>
          </>
        ) : (
          <>
            <Input
              value={tm.editUserForm.phone_number ?? ""}
              onChange={(e) => tm.handleEditUserPhoneChange(e.target.value)}
            />
            <FormErrorMessage>{tm.editUserFormErrors.phone_number}</FormErrorMessage>
            <FieldHint show={!tm.editUserFormErrors.phone_number}>
              {FIELD_HINTS.tenantUser.phone.helper}
            </FieldHint>
          </>
        )}
      </FormControl>
    </VStack>
  );
}
