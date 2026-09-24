import React from "react";
import { INSTITUTION } from "../../config/constants";
import FormActions from "../common/FormActions";
import StandardModal from "../common/StandardModal";
import InstitutionForm from "./InstitutionForm";
import { useTenantManagement } from "./hooks/useTenantManagement";

type EditInstitutionModalProps = {
  tm: ReturnType<typeof useTenantManagement>;
};

export default function EditInstitutionModal({ tm }: EditInstitutionModalProps) {
  return (
    <StandardModal
      isOpen={tm.isEditTenantModalOpen}
      onClose={tm.closeEditTenantModal}
      size="2xl"
      scrollBehavior="inside"
      title={`Edit ${INSTITUTION}`}
      description={`Update the ${INSTITUTION.toLowerCase()} details.`}
      modalProps={{ blockScrollOnMount: true }}
      headerProps={{ px: 6, pt: 5, pb: 4 }}
      bodyProps={{ px: 6, py: 5 }}
      footerProps={{ px: 6, py: 4 }}
      footer={
        <FormActions
          submitLabel="Save Changes"
          onCancel={tm.closeEditTenantModal}
          onSubmit={tm.handleSaveEditTenant}
          isLoading={tm.isSubmittingEditTenant}
          isDisabled={!tm.canSubmitEditTenantForm}
          loadingText="Saving..."
          justify="space-between"
          pt={0}
        />
      }
    >
      <InstitutionForm
        mode="edit"
        values={{
          organisation: tm.editTenantForm.organisation ?? "",
          contact_name: tm.editTenantForm.contact_name ?? "",
          email: tm.editTenantForm.email ?? "",
          phone_number: tm.editTenantForm.phone_number ?? "",
        }}
        errors={tm.editTenantFormErrors}
        emailEditable={tm.isEditTenantEmailEditable}
        emailStatus={tm.editTenantEmailStatus}
        onOrganisationChange={tm.handleEditTenantOrganisationChange}
        onOrganisationBlur={tm.handleEditTenantOrganisationBlur}
        onContactNameChange={tm.handleEditTenantContactNameChange}
        onEmailChange={tm.handleEditTenantEmailChange}
        onPhoneChange={tm.handleEditTenantPhoneChange}
      />
    </StandardModal>
  );
}
