import { Badge, Text } from "@chakra-ui/react";
import React, { useEffect, useState } from "react";
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
import FormDrawer from "../common/FormDrawer";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";
import type { TenantUserView } from "../../types/tenant";
import InstitutionUserForm from "./InstitutionUserForm";

type InstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
  resolveUserDisplayStatus: (user: TenantUserView) => TenantUserStatusValue;
};

/** One host for add, edit, and view. The fields live in InstitutionUserForm. */
export default function InstitutionUserModal({
  tm,
  resolveUserDisplayStatus,
}: InstitutionUserModalProps) {
  const [userConsentAccepted, setUserConsentAccepted] = useState(false);
  const [userConsentError, setUserConsentError] = useState("");

  const isEdit = tm.isEditUserModalOpen;
  const isCreate = tm.isUserModalOpen;
  const viewUser = tm.viewUserDetail;
  const isView = tm.isViewUserModalOpen && Boolean(viewUser);

  useEffect(() => {
    setUserConsentAccepted(false);
    setUserConsentError("");
  }, [tm.isUserModalOpen]);

  const closeActive = () => {
    if (isEdit) {
      if (tm.isSubmittingEditUser) return;
      tm.closeEditUserModal();
      return;
    }
    if (isCreate) {
      if (tm.isSubmittingUser) return;
      tm.closeUserModal();
      return;
    }
    if (isView) tm.closeViewUserModal();
  };

  const editTitle =
    tm.editUserForm.full_name?.trim() ||
    tm.editUserRow?.full_name?.trim() ||
    tm.editUserRow?.username ||
    "Edit User";
  const viewTitle =
    viewUser?.full_name?.trim() || viewUser?.username || "User";

  return (
    <FormDrawer
      isOpen={isEdit || isCreate || isView}
      onClose={closeActive}
      title={
        isEdit
          ? editTitle
          : isCreate
            ? `Add ${INSTITUTION} User`
            : viewTitle
      }
      description={
        isEdit
          ? "Update the user's details."
          : isCreate
            ? `Invite someone to this ${INSTITUTION.toLowerCase()}.`
            : "View the user's information."
      }
      footer={
        isEdit ? (
          <FormActions
            cancelLabel="Cancel"
            submitLabel="Save Changes"
            onCancel={closeActive}
            onSubmit={tm.handleSaveEditUser}
            isLoading={tm.isSubmittingEditUser}
            isDisabled={!tm.canSubmitEditUserForm}
            loadingText="Saving..."
            justify="space-between"
            pt={0}
          />
        ) : isCreate ? (
          <FormActions
            cancelLabel="Cancel"
            submitLabel="Add User"
            onCancel={closeActive}
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
        ) : (
          <FormActions hideSubmit cancelLabel="Back" onCancel={closeActive} pt={0} />
        )
      }
    >
      {isEdit ? (
        <InstitutionUserForm mode="edit" tm={tm} />
      ) : isCreate ? (
        <>
          <InstitutionUserForm mode="create" tm={tm} />
          <ConsentCheckbox
            isChecked={userConsentAccepted}
            onChange={(checked) => {
              setUserConsentAccepted(checked);
              if (checked) setUserConsentError("");
            }}
            error={userConsentError}
          />
        </>
      ) : viewUser ? (
        <>
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
        </>
      ) : null}
    </FormDrawer>
  );
}
