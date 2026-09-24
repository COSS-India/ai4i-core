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
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import StandardModal from "../common/StandardModal";
import { dash } from "../../utils/valueFormatters";
import {
  DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
  formatPlatformRoleLabel,
  isDefaultTenant,
} from "../../utils/defaultTenant";
import { TENANT_USER_ROLE_OPTIONS } from "../profile/types";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";

type EditInstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
};

export default function EditInstitutionUserModal({ tm }: EditInstitutionUserModalProps) {
  const editUserRoleOptions = useMemo((): ReadonlyArray<{
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
      // Preserve non-assignable current roles (e.g. Admin) so profile-only edits
      // do not force a demotion.
      return [
        {
          value: current,
          label: formatPlatformRoleLabel(current),
        },
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
    <StandardModal
      isOpen={tm.isEditUserModalOpen}
      onClose={tm.closeEditUserModal}
      size="2xl"
      scrollBehavior="inside"
      title="Edit User"
      description="Update the user's details."
      modalProps={{ blockScrollOnMount: true }}
      headerProps={{ px: 6, pt: 5, pb: 4 }}
      bodyProps={{ px: 6, py: 5 }}
      footerProps={{ px: 6, py: 4 }}
      footer={
        <FormActions
          submitLabel="Save Changes"
          onCancel={tm.closeEditUserModal}
          onSubmit={tm.handleSaveEditUser}
          isLoading={tm.isSubmittingEditUser}
          isDisabled={!tm.canSubmitEditUserForm}
          loadingText="Saving..."
          justify="space-between"
          pt={0}
        />
      }
    >
      <VStack spacing={4} align="stretch">
        <FormControl
          isRequired
          isInvalid={Boolean(tm.editUserFormErrors.username)}
        >
          <FieldLabel>Username</FieldLabel>
          <Input
            value={tm.editUserForm.username ?? ""}
            onChange={(e) =>
              tm.handleEditUserUsernameChange(e.target.value)
            }
            maxLength={100}
          />
          <FormErrorMessage>
            {tm.editUserFormErrors.username}
          </FormErrorMessage>
          <FieldHint show={!tm.editUserFormErrors.username}>
            {FIELD_HINTS.tenantUser.username.helper}
          </FieldHint>
        </FormControl>
        <FormControl>
          <FieldLabel>Email</FieldLabel>
          <Text fontSize="md" color="ink.700" py={1}>
            {dash(tm.editUserRow?.email)}
          </Text>
          <FieldHint>{FIELD_HINTS.tenantUser.emailLocked}</FieldHint>
        </FormControl>
        <FormControl isInvalid={Boolean(tm.editUserFormErrors.full_name)}>
          <FieldLabel>Full Name</FieldLabel>
          <Input
            value={tm.editUserForm.full_name ?? ""}
            onChange={(e) =>
              tm.handleEditUserFullNameChange(e.target.value)
            }
          />
          <FormErrorMessage>
            {tm.editUserFormErrors.full_name}
          </FormErrorMessage>
          <FieldHint show={!tm.editUserFormErrors.full_name}>
            {FIELD_HINTS.tenantUser.fullName.helper}
          </FieldHint>
        </FormControl>
        <FormControl>
          <FieldLabel required>Role</FieldLabel>
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
            {editUserRoleOptions.map((opt) => (
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
        </FormControl>
        <FormControl
          isInvalid={Boolean(tm.editUserFormErrors.phone_number)}
        >
          <FieldLabel>Phone Number</FieldLabel>
          <Input
            value={tm.editUserForm.phone_number ?? ""}
            onChange={(e) => tm.handleEditUserPhoneChange(e.target.value)}
          />
          <FormErrorMessage>
            {tm.editUserFormErrors.phone_number}
          </FormErrorMessage>
          <FieldHint show={!tm.editUserFormErrors.phone_number}>
            {FIELD_HINTS.tenantUser.phone.helper}
          </FieldHint>
        </FormControl>
      </VStack>
    </StandardModal>
  );
}
