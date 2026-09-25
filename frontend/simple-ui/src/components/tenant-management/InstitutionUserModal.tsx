import { Badge, Box, Text, VStack } from "@chakra-ui/react";
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
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import StandardModal, { CreateModal } from "../common/StandardModal";
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

  useEffect(() => {
    setUserConsentAccepted(false);
    setUserConsentError("");
  }, [tm.isUserModalOpen]);

  const viewUser = tm.viewUserDetail;

  return (
    <>
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
          <InstitutionUserForm mode="create" tm={tm} />
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
        <InstitutionUserForm mode="edit" tm={tm} />
      </StandardModal>

      <StandardModal
        isOpen={tm.isViewUserModalOpen}
        onClose={tm.closeViewUserModal}
        size="xl"
        scrollBehavior="inside"
        title="User Details"
        description="View the user's information."
        modalProps={{ blockScrollOnMount: true }}
        headerProps={{ px: 6, pt: 5, pb: 4 }}
        bodyProps={{ px: 6, py: 5 }}
        footerProps={{ px: 6, py: 4 }}
        footer={
          <FormActions
            cancelLabel="Close"
            onCancel={tm.closeViewUserModal}
            hideSubmit
            justify="flex-end"
            pt={0}
          />
        }
      >
        {viewUser ? (
          <VStack align="stretch" spacing={4}>
            <InstitutionUserForm mode="view" tm={tm} />
            <Box>
              <FieldLabel variant="inline">User ID</FieldLabel>
              <Text fontFamily="mono">{viewUser.user_id}</Text>
            </Box>
            <Box>
              <FieldLabel variant="inline">Status</FieldLabel>
              <Badge
                colorScheme={getTenantStatusColorScheme(
                  resolveUserDisplayStatus(viewUser),
                )}
              >
                {formatTenantUserStatusLabel(resolveUserDisplayStatus(viewUser))}
              </Badge>
            </Box>
          </VStack>
        ) : (
          <Text>No user selected.</Text>
        )}
      </StandardModal>
    </>
  );
}
