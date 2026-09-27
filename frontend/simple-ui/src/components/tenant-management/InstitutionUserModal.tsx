import { Badge, HStack, Text } from "@chakra-ui/react";
import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  INSTITUTION,
  formatTenantUserStatusLabel,
  getTenantStatusColorScheme,
  type TenantUserStatusValue,
} from "../../config/constants";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import FormActions from "../common/FormActions";
import FormPage from "../common/FormPage";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";
import type { TenantUserView } from "../../types/tenant";
import InstitutionUserForm from "./InstitutionUserForm";

type InstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
  resolveUserDisplayStatus: (user: TenantUserView) => TenantUserStatusValue;
  /** Renders Create/Edit/View outside the institution page chrome. */
  formHost?: HTMLElement | null;
  onFormOpenChange?: (open: boolean) => void;
};

/** One host for add, edit, and view. The fields live in InstitutionUserForm. */
export default function InstitutionUserModal({
  tm,
  resolveUserDisplayStatus,
  formHost = null,
  onFormOpenChange,
}: InstitutionUserModalProps) {
  const [userConsentAccepted, setUserConsentAccepted] = useState(false);
  const [userConsentError, setUserConsentError] = useState("");

  const formOpen =
    tm.isUserModalOpen || tm.isEditUserModalOpen || tm.isViewUserModalOpen;

  useEffect(() => {
    setUserConsentAccepted(false);
    setUserConsentError("");
  }, [tm.isUserModalOpen]);

  useEffect(() => {
    onFormOpenChange?.(formOpen);
    return () => onFormOpenChange?.(false);
  }, [formOpen, onFormOpenChange]);

  const closeUserForms = () => {
    tm.closeUserModal();
    tm.closeEditUserModal();
    tm.closeViewUserModal();
  };

  const parent = {
    label: `${INSTITUTION} Management`,
    href: "/institution-management",
    onNavigate: closeUserForms,
  };

  const viewUser = tm.viewUserDetail;
  const editTitle =
    tm.editUserForm.full_name?.trim() ||
    tm.editUserRow?.full_name?.trim() ||
    tm.editUserRow?.username ||
    "Edit User";
  const viewTitle =
    viewUser?.full_name?.trim() || viewUser?.username || "User";

  const page = tm.isEditUserModalOpen ? (
    <FormPage
      title={editTitle}
      description="Update the user's details."
      parent={parent}
      onLeave={tm.closeEditUserModal}
      footer={({ leave }) => (
        <FormActions
          cancelLabel="Cancel"
          submitLabel="Save Changes"
          onCancel={leave}
          onSubmit={tm.handleSaveEditUser}
          isLoading={tm.isSubmittingEditUser}
          isDisabled={!tm.canSubmitEditUserForm}
          loadingText="Saving..."
          justify="space-between"
          pt={0}
        />
      )}
    >
      <InstitutionUserForm mode="edit" tm={tm} />
    </FormPage>
  ) : tm.isUserModalOpen ? (
    <FormPage
      title={`Add ${INSTITUTION} User`}
      description={`Invite someone to this ${INSTITUTION.toLowerCase()}.`}
      parent={parent}
      onLeave={tm.closeUserModal}
      footer={({ leave }) => (
        <FormActions
          cancelLabel="Cancel"
          submitLabel="Add User"
          onCancel={leave}
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
      )}
    >
      <InstitutionUserForm mode="create" tm={tm} />
      <ConsentCheckbox
        isChecked={userConsentAccepted}
        onChange={(checked) => {
          setUserConsentAccepted(checked);
          if (checked) setUserConsentError("");
        }}
        error={userConsentError}
      />
    </FormPage>
  ) : tm.isViewUserModalOpen && viewUser ? (
    <FormPage
      title={viewTitle}
      description="View the user's information."
      parent={parent}
      onLeave={tm.closeViewUserModal}
      actions={
        <HStack spacing={2}>
          <Badge
            colorScheme={getTenantStatusColorScheme(
              resolveUserDisplayStatus(viewUser),
            )}
          >
            {formatTenantUserStatusLabel(resolveUserDisplayStatus(viewUser))}
          </Badge>
        </HStack>
      }
      footer={({ leave }) => (
        <FormActions hideSubmit cancelLabel="Back" onCancel={leave} pt={0} />
      )}
    >
      <InstitutionUserForm mode="view" tm={tm} />
      <FormSection title="Record">
        <ReadOnlyField label="User ID">
          <Text fontFamily="mono" fontSize="sm">{viewUser.user_id}</Text>
        </ReadOnlyField>
        <ReadOnlyField label="Status">
          <Badge
            colorScheme={getTenantStatusColorScheme(
              resolveUserDisplayStatus(viewUser),
            )}
          >
            {formatTenantUserStatusLabel(resolveUserDisplayStatus(viewUser))}
          </Badge>
        </ReadOnlyField>
      </FormSection>
    </FormPage>
  ) : null;

  if (!page) return null;
  return formHost ? createPortal(page, formHost) : page;
}
