import React from "react";
import FormActions from "../common/FormActions";
import StandardModal from "../common/StandardModal";
import { useTenantManagement } from "../profile/hooks/useTenantManagement";
import InstitutionUserForm from "./InstitutionUserForm";

type EditInstitutionUserModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
};

export default function EditInstitutionUserModal({ tm }: EditInstitutionUserModalProps) {
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
      <InstitutionUserForm mode="edit" tm={tm} />
    </StandardModal>
  );
}
