import {
  FormControl,
  FormErrorMessage,
  Input,
  VStack,
} from "@chakra-ui/react";
import React, { useState } from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import { INSTITUTION } from "../../config/constants";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormActions from "../common/FormActions";
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
        <FormControl isRequired isInvalid={Boolean(tm.tenantFormErrors.organisation)}>
          <FieldLabel>Organisation</FieldLabel>
          <Input
            value={tm.tenantForm.organisation}
            onChange={(e) => tm.handleTenantOrganisationChange(e.target.value)}
            onBlur={(e) => tm.handleTenantOrganisationBlur(e.target.value)}
            placeholder={FIELD_HINTS.tenant.organisation.placeholder}
            maxLength={100}
          />
          <FormErrorMessage>{tm.tenantFormErrors.organisation}</FormErrorMessage>
          <FieldHint show={!tm.tenantFormErrors.organisation}>
            {FIELD_HINTS.tenant.organisation.helper}
          </FieldHint>
        </FormControl>
        <FormControl isRequired isInvalid={Boolean(tm.tenantFormErrors.contact_name)}>
          <FieldLabel>Contact Name</FieldLabel>
          <Input
            value={tm.tenantForm.contact_name}
            onChange={(e) => tm.handleTenantContactNameChange(e.target.value)}
            onBlur={(e) => tm.handleTenantContactNameBlur(e.target.value)}
            placeholder={FIELD_HINTS.tenant.contactName.placeholder}
          />
          <FormErrorMessage>{tm.tenantFormErrors.contact_name}</FormErrorMessage>
          <FieldHint show={!tm.tenantFormErrors.contact_name}>
            {FIELD_HINTS.tenant.contactName.helper}
          </FieldHint>
        </FormControl>
        <FormControl isRequired isInvalid={Boolean(tm.tenantFormErrors.email)}>
          <FieldLabel>Email</FieldLabel>
          <Input
            type="email"
            value={tm.tenantForm.email}
            onChange={(e) => tm.handleTenantEmailChange(e.target.value)}
            onBlur={tm.handleTenantEmailBlur}
            placeholder={FIELD_HINTS.tenant.email.placeholder}
          />
          <FormErrorMessage>{tm.tenantFormErrors.email}</FormErrorMessage>
          <FieldHint
            show={!tm.tenantFormErrors.email}
            tone={tm.tenantEmailStatus === "available" ? "success" : "muted"}
          >
            {tm.tenantEmailStatus === "checking"
              ? FIELD_HINTS.tenant.emailChecking
              : tm.tenantEmailStatus === "available"
                ? FIELD_HINTS.tenant.emailAvailable
                : FIELD_HINTS.tenant.email.helper}
          </FieldHint>
        </FormControl>
        <FormControl isInvalid={Boolean(tm.tenantFormErrors.phone_number)}>
          <FieldLabel>Phone Number</FieldLabel>
          <Input
            value={tm.tenantForm.phone_number}
            onChange={(e) => tm.handleTenantPhoneChange(e.target.value)}
            placeholder={FIELD_HINTS.tenant.phone.placeholder}
          />
          <FormErrorMessage>{tm.tenantFormErrors.phone_number}</FormErrorMessage>
          <FieldHint show={!tm.tenantFormErrors.phone_number}>
            {FIELD_HINTS.tenant.phone.helper}
          </FieldHint>
        </FormControl>
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
