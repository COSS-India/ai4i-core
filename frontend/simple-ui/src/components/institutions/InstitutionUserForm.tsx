import {
  Box,
  FormControl,
  FormErrorMessage,
  Input,
  Select,
  Tooltip,
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
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
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
import { useTenantManagement } from "./hooks/useTenantManagement";

export type InstitutionUserFormMode = "create" | "edit" | "view";

type TenantManagement = ReturnType<typeof useTenantManagement>;

type InstitutionUserFormProps = Readonly<{
  mode: InstitutionUserFormMode;
  tm: TenantManagement;
}>;

type TenantFieldProps = Readonly<{ tm: TenantManagement }>;

function getCreateEmailHint(status: TenantManagement["userEmailStatus"]): string {
  if (status === "checking") return FIELD_HINTS.tenant.emailChecking;
  if (status === "available") return FIELD_HINTS.tenant.emailAvailable;
  return FIELD_HINTS.tenantUser.email.helper;
}

/** Create-only, platform admin only. Locked when opened from an institution. */
function InstitutionPickerField({ tm }: TenantFieldProps) {
  if (tm.lockedUserFormTenantId) {
    return (
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
    );
  }

  return (
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
  );
}

function UsernameField({ mode, tm }: InstitutionUserFormProps) {
  if (mode === "view") {
    return (
      <ReadOnlyField label="Username">{dash(tm.viewUserDetail?.username)}</ReadOnlyField>
    );
  }
  if (mode === "edit") {
    return (
      <FormControl isRequired isInvalid={Boolean(tm.editUserFormErrors.username)}>
        <FieldLabel>Username</FieldLabel>
        <Input
          value={tm.editUserForm.username ?? ""}
          onChange={(e) => tm.handleEditUserUsernameChange(e.target.value)}
          maxLength={100}
        />
        <FormErrorMessage>{tm.editUserFormErrors.username}</FormErrorMessage>
        <FieldHint show={!tm.editUserFormErrors.username}>
          {FIELD_HINTS.tenantUser.username.helper}
        </FieldHint>
      </FormControl>
    );
  }
  return null;
}

function EmailField({ mode, tm }: InstitutionUserFormProps) {
  if (mode === "create") {
    return (
      <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.email)}>
        <FieldLabel>Email</FieldLabel>
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
          {getCreateEmailHint(tm.userEmailStatus)}
        </FieldHint>
      </FormControl>
    );
  }
  if (mode === "view") {
    return <ReadOnlyField label="Email">{dash(tm.viewUserDetail?.email)}</ReadOnlyField>;
  }
  return (
    <FormControl>
      <ReadOnlyField label="Email">{dash(tm.editUserRow?.email)}</ReadOnlyField>
      <FieldHint>{FIELD_HINTS.tenantUser.emailLocked}</FieldHint>
    </FormControl>
  );
}

function FullNameField({ mode, tm }: InstitutionUserFormProps) {
  if (mode === "view") {
    return (
      <ReadOnlyField label="Full Name">{dash(tm.viewUserDetail?.full_name)}</ReadOnlyField>
    );
  }
  if (mode === "create") {
    return (
      <FormControl isRequired isInvalid={Boolean(tm.userFormErrors.full_name)}>
        <FieldLabel>Full Name</FieldLabel>
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
      </FormControl>
    );
  }
  return (
    <FormControl isInvalid={Boolean(tm.editUserFormErrors.full_name)}>
      <FieldLabel>Full Name</FieldLabel>
      <Input
        value={tm.editUserForm.full_name ?? ""}
        onChange={(e) => tm.handleEditUserFullNameChange(e.target.value)}
      />
      <FormErrorMessage>{tm.editUserFormErrors.full_name}</FormErrorMessage>
      <FieldHint show={!tm.editUserFormErrors.full_name}>
        {FIELD_HINTS.tenantUser.fullName.helper}
      </FieldHint>
    </FormControl>
  );
}

function CreateRoleField({ tm }: TenantFieldProps) {
  const roleOptions = useMemo(() => {
    const tenantId =
      tm.lockedUserFormTenantId ?? tm.userForm.tenant_id?.trim() ?? "";
    const selected = tm.tenants.find((t) => t.tenant_id === tenantId);
    if (selected && isDefaultTenant(selected)) {
      return DEFAULT_ORG_USER_FORM_ROLE_OPTIONS;
    }
    return TENANT_USER_ROLE_OPTIONS;
  }, [tm.lockedUserFormTenantId, tm.userForm.tenant_id, tm.tenants]);

  return (
    <FormControl isRequired>
      <FieldLabel>Role</FieldLabel>
      <Select
        value={tm.userForm.role}
        onChange={(e) =>
          tm.setUserForm({
            ...tm.userForm,
            role: e.target.value as typeof tm.userForm.role,
          })
        }
      >
        {roleOptions.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </Select>
      <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
    </FormControl>
  );
}

function EditRoleField({ tm }: TenantFieldProps) {
  const roleOptions = useMemo((): ReadonlyArray<{
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
    <FormControl>
      <FieldLabel required>Role</FieldLabel>
      {/* Disabled controls swallow hover, so the tooltip targets a wrapper. */}
      <Tooltip
        label={FIELD_HINTS.tenantUser.selfRegisteredRoleLocked}
        placement="top"
        hasArrow
        openDelay={300}
        isDisabled={!tm.isEditUserSelfRegistered}
      >
        <Box tabIndex={tm.isEditUserSelfRegistered ? 0 : undefined}>
          <Select
            value={tm.editUserForm.role}
            isDisabled={
              !tm.editUserRolesLoaded ||
              tm.isEditUserOnlyAdmin ||
              tm.isEditUserSelfRegistered
            }
            onChange={(e) =>
              tm.setEditUserForm({
                ...tm.editUserForm,
                role: e.target.value as typeof tm.editUserForm.role,
              })
            }
          >
            {roleOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </Box>
      </Tooltip>
      {!tm.editUserRolesLoaded && (
        <FieldHint>{FIELD_HINTS.tenantUser.rolesLoadFailed}</FieldHint>
      )}
      {tm.isEditUserSelfRegistered && (
        <FieldHint>{FIELD_HINTS.tenantUser.selfRegisteredRoleLocked}</FieldHint>
      )}
      {tm.isEditUserOnlyAdmin && !tm.isEditUserSelfRegistered && (
        <FieldHint>{FIELD_HINTS.tenantUser.onlyAdminLocked}</FieldHint>
      )}
      {!tm.isEditUserOnlyAdmin &&
        !tm.isEditUserSelfRegistered &&
        tm.editUserRolesLoaded && (
          <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
        )}
    </FormControl>
  );
}

function RoleField({ mode, tm }: InstitutionUserFormProps) {
  const viewUser = tm.viewUserDetail;
  if (mode === "view" && viewUser) {
    return (
      <ReadOnlyField label="Roles">
        <TenantUserRoleBadges
          role={viewUser.role}
          roles={viewUser.roles}
          badgeFontSize="sm"
        />
      </ReadOnlyField>
    );
  }
  if (mode === "create") return <CreateRoleField tm={tm} />;
  return <EditRoleField tm={tm} />;
}

function PhoneField({ mode, tm }: InstitutionUserFormProps) {
  if (mode === "view") {
    return (
      <ReadOnlyField label="Phone Number">
        {dash(tm.viewUserDetail?.phone_number)}
      </ReadOnlyField>
    );
  }
  if (mode === "create") {
    return (
      <FormControl isInvalid={Boolean(tm.userFormErrors.phone_number)}>
        <FieldLabel>Phone Number</FieldLabel>
        <Input
          value={tm.userForm.phone_number}
          onChange={(e) => tm.handleUserPhoneChange(e.target.value)}
          placeholder={FIELD_HINTS.tenantUser.phone.placeholder}
        />
        <FormErrorMessage>{tm.userFormErrors.phone_number}</FormErrorMessage>
        <FieldHint show={!tm.userFormErrors.phone_number}>
          {FIELD_HINTS.tenantUser.phone.helper}
        </FieldHint>
      </FormControl>
    );
  }
  return (
    <FormControl isInvalid={Boolean(tm.editUserFormErrors.phone_number)}>
      <FieldLabel>Phone Number</FieldLabel>
      <Input
        value={tm.editUserForm.phone_number ?? ""}
        onChange={(e) => tm.handleEditUserPhoneChange(e.target.value)}
      />
      <FormErrorMessage>{tm.editUserFormErrors.phone_number}</FormErrorMessage>
      <FieldHint show={!tm.editUserFormErrors.phone_number}>
        {FIELD_HINTS.tenantUser.phone.helper}
      </FieldHint>
    </FormControl>
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

  return (
    <FormSection title="User">
      <VStack spacing={4} align="stretch">
        {mode === "create" && isAdmin && <InstitutionPickerField tm={tm} />}
        <UsernameField mode={mode} tm={tm} />
        <EmailField mode={mode} tm={tm} />
        <FullNameField mode={mode} tm={tm} />
        <RoleField mode={mode} tm={tm} />
        <PhoneField mode={mode} tm={tm} />
      </VStack>
    </FormSection>
  );
}
