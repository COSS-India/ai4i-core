import {
  FormControl,
  FormErrorMessage,
  Input,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import { INSTITUTION } from "../../config/constants";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
import StandardModal from "../common/StandardModal";
import { dash } from "../../utils/valueFormatters";
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
      <VStack spacing={4} align="stretch">
        <FormControl
          isRequired
          isInvalid={Boolean(tm.editTenantFormErrors.organisation)}
        >
          <FieldLabel>Organisation</FieldLabel>
          <Input
            value={tm.editTenantForm.organisation ?? ""}
            onChange={(e) =>
              tm.handleEditTenantOrganisationChange(e.target.value)
            }
            onBlur={(e) =>
              tm.handleEditTenantOrganisationBlur(e.target.value)
            }
            maxLength={100}
          />
          <FormErrorMessage>
            {tm.editTenantFormErrors.organisation}
          </FormErrorMessage>
          <FieldHint show={!tm.editTenantFormErrors.organisation}>
            {FIELD_HINTS.tenant.organisation.helper}
          </FieldHint>
        </FormControl>
        <FormControl
          isInvalid={Boolean(tm.editTenantFormErrors.contact_name)}
        >
          <FieldLabel>Contact Name</FieldLabel>
          <Input
            value={tm.editTenantForm.contact_name ?? ""}
            onChange={(e) =>
              tm.handleEditTenantContactNameChange(e.target.value)
            }
          />
          <FormErrorMessage>
            {tm.editTenantFormErrors.contact_name}
          </FormErrorMessage>
          <FieldHint show={!tm.editTenantFormErrors.contact_name}>
            {FIELD_HINTS.tenant.contactName.helper}
          </FieldHint>
        </FormControl>
        <FormControl
          isRequired={tm.isEditTenantEmailEditable}
          isInvalid={
            tm.isEditTenantEmailEditable &&
            Boolean(tm.editTenantFormErrors.email)
          }
        >
          <FieldLabel>Email</FieldLabel>
          {tm.isEditTenantEmailEditable ? (
            <>
              <Input
                type="email"
                value={tm.editTenantForm.email ?? ""}
                onChange={(e) =>
                  tm.handleEditTenantEmailChange(e.target.value)
                }
              />
              <FormErrorMessage>
                {tm.editTenantFormErrors.email}
              </FormErrorMessage>
              <FieldHint show={!tm.editTenantFormErrors.email}>
                {FIELD_HINTS.tenant.emailVerifyOnChange}
              </FieldHint>
              <FieldHint
                show={
                  !tm.editTenantFormErrors.email &&
                  (tm.editTenantEmailStatus === "checking" ||
                    tm.editTenantEmailStatus === "available")
                }
                tone={
                  tm.editTenantEmailStatus === "available" ? "success" : "muted"
                }
              >
                {tm.editTenantEmailStatus === "checking"
                  ? FIELD_HINTS.tenant.emailChecking
                  : FIELD_HINTS.tenant.emailAvailable}
              </FieldHint>
            </>
          ) : (
            <>
              <Text fontSize="md" color="ink.700" py={1}>
                {dash(tm.editTenantForm.email)}
              </Text>
              <FieldHint>{FIELD_HINTS.tenant.emailPendingOnly}</FieldHint>
            </>
          )}
        </FormControl>
        <FormControl
          isInvalid={Boolean(tm.editTenantFormErrors.phone_number)}
        >
          <FieldLabel>Phone Number</FieldLabel>
          <Input
            value={tm.editTenantForm.phone_number ?? ""}
            onChange={(e) =>
              tm.handleEditTenantPhoneChange(e.target.value)
            }
          />
          <FormErrorMessage>
            {tm.editTenantFormErrors.phone_number}
          </FormErrorMessage>
          <FieldHint show={!tm.editTenantFormErrors.phone_number}>
            {FIELD_HINTS.tenant.phone.helper}
          </FieldHint>
        </FormControl>
      </VStack>
    </StandardModal>
  );
}
