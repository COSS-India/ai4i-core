import { VStack } from "@chakra-ui/react";
import React, { useState } from "react";
import { INSTITUTION } from "../../config/constants";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import FormActions from "../common/FormActions";
import InstitutionForm from "./InstitutionForm";
import { useTenantManagement } from "./hooks/useTenantManagement";

type CreateInstitutionFormProps = {
  tm: ReturnType<typeof useTenantManagement>;
  onCancel?: () => void;
  onCreated?: () => void;
  hideActions?: boolean;
  formId?: string;
  onConsentChange?: (accepted: boolean) => void;
};

const FORM_ID = "create-institution-form";

/** Existing Institution create fields — used inside the shared Create modal. */
export default function CreateInstitutionForm({
  tm,
  onCancel,
  onCreated,
  hideActions = false,
  formId = FORM_ID,
  onConsentChange,
}: CreateInstitutionFormProps) {
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [consentError, setConsentError] = useState("");

  const handleSubmit = () => {
    const nextError = getConsentValidationError(consentAccepted);
    if (nextError) {
      setConsentError(nextError);
      return;
    }
    void tm.handleRegisterTenant().then((ok) => {
      if (ok) onCreated?.();
    });
  };

  return (
    <form
      id={formId}
      onSubmit={(e) => {
        e.preventDefault();
        handleSubmit();
      }}
    >
      <VStack spacing={4} align="stretch">
        <InstitutionForm
          mode="create"
          values={tm.tenantForm}
          errors={tm.tenantFormErrors}
          emailStatus={tm.tenantEmailStatus}
          onOrganisationChange={tm.handleTenantOrganisationChange}
          onOrganisationBlur={tm.handleTenantOrganisationBlur}
          onContactNameChange={tm.handleTenantContactNameChange}
          onContactNameBlur={tm.handleTenantContactNameBlur}
          onEmailChange={tm.handleTenantEmailChange}
          onEmailBlur={tm.handleTenantEmailBlur}
          onPhoneChange={tm.handleTenantPhoneChange}
        />
        <ConsentCheckbox
          isChecked={consentAccepted}
          onChange={(checked) => {
            setConsentAccepted(checked);
            onConsentChange?.(checked);
            if (checked) setConsentError("");
          }}
          error={consentError}
        />
        {!hideActions && onCancel ? (
          <FormActions
            cancelLabel="Cancel"
            submitLabel={`Create ${INSTITUTION}`}
            onCancel={onCancel}
            isLoading={tm.isSubmittingTenant}
            loadingText="Creating..."
            isDisabled={!tm.canSubmitTenantForm || !consentAccepted}
            submitType="submit"
          />
        ) : null}
      </VStack>
    </form>
  );
}

export { FORM_ID as CREATE_INSTITUTION_FORM_ID };
