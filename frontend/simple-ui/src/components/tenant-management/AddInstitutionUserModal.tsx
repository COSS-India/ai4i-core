import { VStack } from "@chakra-ui/react";
import React, { useEffect, useState } from "react";
import { INSTITUTION } from "../../config/constants";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import FormActions from "../common/FormActions";
import { CreateModal } from "../common/StandardModal";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";
import InstitutionUserForm from "./InstitutionUserForm";

type AddInstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
};

export default function AddInstitutionUserModal({ tm }: AddInstitutionUserModalProps) {
  const [userConsentAccepted, setUserConsentAccepted] = useState(false);
  const [userConsentError, setUserConsentError] = useState("");

  useEffect(() => {
    setUserConsentAccepted(false);
    setUserConsentError("");
  }, [tm.isUserModalOpen]);

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
  );
}
