import {
  FormControl,
  FormErrorMessage,
  Input,
  Select,
  VStack,
} from "@chakra-ui/react";
import React, { useEffect, useMemo, useState } from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import {
  INSTITUTION,
  INSTITUTION_ARTICLE,
} from "../../config/constants";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import { CreateModal } from "../common/StandardModal";
import { useAuth } from "../../hooks/useAuth";
import { isPlatformAdminUser } from "../../utils/rbac";
import {
  DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
  isDefaultTenant,
} from "../../utils/defaultTenant";
import { TENANT_USER_ROLE_OPTIONS } from "../profile/types";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";

type AddInstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
};

export default function AddInstitutionUserModal({ tm }: AddInstitutionUserModalProps) {
  const { user } = useAuth();
  const isAdmin = isPlatformAdminUser(user?.roles);

  const [userConsentAccepted, setUserConsentAccepted] = useState(false);
  const [userConsentError, setUserConsentError] = useState("");

  useEffect(() => {
    setUserConsentAccepted(false);
    setUserConsentError("");
  }, [tm.isUserModalOpen]);

  const userFormRoleOptions = useMemo(() => {
    const tenantId =
      tm.lockedUserFormTenantId ?? tm.userForm.tenant_id?.trim() ?? "";
    const selected = tm.tenants.find((t) => t.tenant_id === tenantId);
    if (selected && isDefaultTenant(selected)) {
      return DEFAULT_ORG_USER_FORM_ROLE_OPTIONS;
    }
    return TENANT_USER_ROLE_OPTIONS;
  }, [tm.lockedUserFormTenantId, tm.userForm.tenant_id, tm.tenants]);

  return (
    <CreateModal
      isOpen={tm.isUserModalOpen}
      onClose={tm.closeUserModal}
      size="md"
      title={`Add ${INSTITUTION} User`}
      description={`Invite someone to this ${INSTITUTION.toLowerCase()}.`}
      footer={
        <FormActions
          submitLabel="Add User"
          onCancel={tm.closeUserModal}
          isLoading={tm.isSubmittingUser}
          isDisabled={!tm.canSubmitUserForm || !userConsentAccepted}
          loadingText="Adding..."
          justify="space-between"
          pt={0}
          onSubmit={() => {
            const consentError = getConsentValidationError(userConsentAccepted);
            if (consentError) {
              setUserConsentError(consentError);
              return;
            }
            tm.handleRegisterUser();
          }}
        />
      }
    >
      <VStack spacing={4} align="stretch">
        {isAdmin && tm.lockedUserFormTenantId && (
          <FormControl
            isRequired
            isInvalid={Boolean(tm.userFormErrors.tenant_id)}
          >
            <FieldLabel>{INSTITUTION}</FieldLabel>
            <Input
              value={tm.getLockedUserFormTenantLabel()}
              isReadOnly
              bg="ink.50"
              _dark={{ bg: "whiteAlpha.100" }}
              cursor="not-allowed"
            />
            <FormErrorMessage>
              {tm.userFormErrors.tenant_id}
            </FormErrorMessage>
            <FieldHint>{FIELD_HINTS.tenantUser.tenant.helper}</FieldHint>
          </FormControl>
        )}
        {isAdmin && !tm.lockedUserFormTenantId && (
          <FormControl
            isRequired
            isInvalid={Boolean(tm.userFormErrors.tenant_id)}
          >
            <FieldLabel>{INSTITUTION}</FieldLabel>
            <Select
              value={tm.userForm.tenant_id}
              onChange={(e) => tm.setUserFormTenantId(e.target.value)}
            >
              <option value="">Select {INSTITUTION_ARTICLE} {INSTITUTION.toLowerCase()}…</option>
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
            {tm.userEmailStatus === "checking"
              ? FIELD_HINTS.tenant.emailChecking
              : tm.userEmailStatus === "available"
                ? FIELD_HINTS.tenant.emailAvailable
                : FIELD_HINTS.tenantUser.email.helper}
          </FieldHint>
        </FormControl>
        <FormControl
          isRequired
          isInvalid={Boolean(tm.userFormErrors.full_name)}
        >
          <FieldLabel>Full Name</FieldLabel>
          <Input
            value={tm.userForm.full_name}
            onChange={(e) => tm.handleUserFullNameChange(e.target.value)}
            onBlur={(e) => tm.handleUserFullNameBlur(e.target.value)}
            placeholder={FIELD_HINTS.tenantUser.fullName.placeholder}
          />
          <FormErrorMessage>
            {tm.userFormErrors.full_name}
          </FormErrorMessage>
          <FieldHint show={!tm.userFormErrors.full_name}>
            {FIELD_HINTS.tenantUser.fullName.helper}
          </FieldHint>
        </FormControl>
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
            {userFormRoleOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
          <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
        </FormControl>
        <FormControl isInvalid={Boolean(tm.userFormErrors.phone_number)}>
          <FieldLabel>Phone Number</FieldLabel>
          <Input
            value={tm.userForm.phone_number}
            onChange={(e) => tm.handleUserPhoneChange(e.target.value)}
            placeholder={FIELD_HINTS.tenantUser.phone.placeholder}
          />
          <FormErrorMessage>
            {tm.userFormErrors.phone_number}
          </FormErrorMessage>
          <FieldHint show={!tm.userFormErrors.phone_number}>
            {FIELD_HINTS.tenantUser.phone.helper}
          </FieldHint>
        </FormControl>
        <ConsentCheckbox
          isChecked={userConsentAccepted}
          onChange={(checked) => {
            setUserConsentAccepted(checked);
            if (checked) setUserConsentError("");
          }}
          error={userConsentError}
        />
      </VStack>
    </CreateModal>
  );
}
