import { useCallback, useMemo, useState } from "react";
import * as tenantService from "../../../../../services/tenantService";
import { extractErrorInfo } from "../../../../../utils/errorHandler";
import {
  setFieldError,
  validateContactName,
  validateE164Phone,
  validateOrganisation,
  validateOrganisationUnique,
} from "../../../../../utils/tenantFormValidation";
import type { TenantView } from "../../../../../types/tenant";
import type { TenantFormState } from "../../../types";
import { useEmailAvailabilityField } from "../../useEmailAvailabilityField";
import type { TenantEmailRegistryState, TenantModalBaseOptions } from "./types";
import {
  collectCreateTenantErrors,
  emailAvailabilityConfirmed,
} from "./tenantModalValidation";

export interface UseCreateTenantModalOptions extends TenantModalBaseOptions {
  tenants: TenantView[];
  emailRegistry: TenantEmailRegistryState;
}

export function useCreateTenantModal({
  toast,
  tenants,
  refreshLists,
  emailRegistry,
}: UseCreateTenantModalOptions) {
  const [isTenantModalOpen, setIsTenantModalOpen] = useState(false);
  const [tenantForm, setTenantForm] = useState<TenantFormState>({
    organisation: "",
    contact_name: "",
    email: "",
    phone_number: "",
  });
  const [tenantFormErrors, setTenantFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingTenant, setIsSubmittingTenant] = useState(false);

  const patchTenantFormError = useCallback((field: string, error: string | undefined) => {
    setTenantFormErrors((prev) => setFieldError(prev, field, error));
  }, []);

  const getCreateTenantEmailCheckOptions = useCallback(
    () => ({
      mode: "tenant_contact" as const,
      tenantEmails: emailRegistry.knownTenantEmails,
      userEmails: emailRegistry.knownUserEmails,
    }),
    [emailRegistry.knownTenantEmails, emailRegistry.knownUserEmails],
  );

  const emailAvailability = useEmailAvailabilityField({
    enabled: isTenantModalOpen,
    email: tenantForm.email,
    patchError: patchTenantFormError,
    getCheckOptions: getCreateTenantEmailCheckOptions,
    recheckKey: isTenantModalOpen ? emailRegistry.knownEmailRecheckKey : undefined,
  });

  const openTenantModal = () => {
    setTenantForm({ organisation: "", contact_name: "", email: "", phone_number: "" });
    setTenantFormErrors({});
    emailAvailability.clear();
    setIsTenantModalOpen(true);
    void emailRegistry.refreshKnownAccountEmails();
  };

  const closeTenantModal = () => {
    emailAvailability.clear();
    setIsTenantModalOpen(false);
  };

  const handleRegisterTenant = async () => {
    const errors = collectCreateTenantErrors(
      tenantForm,
      tenants,
      emailRegistry.knownTenantEmails,
      emailRegistry.knownUserEmails,
    );
    delete errors.email;
    const emailOk = await emailAvailability.verifyNow();
    if (!emailOk) return;
    if (Object.keys(errors).length > 0) {
      setTenantFormErrors(errors);
      return;
    }
    setTenantFormErrors({});
    setIsSubmittingTenant(true);
    try {
      const created = await tenantService.registerTenant({
        organisation: tenantForm.organisation.trim(),
        contact_name: tenantForm.contact_name.trim(),
        email: tenantForm.email.trim(),
        phone_number: tenantForm.phone_number.trim() || undefined,
      });
      toast({
        title: "Tenant created",
        description: `${created.organisation} is pending activation. The contact will receive a setup link by email.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });
      closeTenantModal();
      await refreshLists(created.tenant_id);
    } catch (err) {
      console.error("Failed to register tenant:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingTenant(false);
    }
  };

  const handleTenantOrganisationChange = (organisation: string) => {
    setTenantForm((prev) => ({ ...prev, organisation }));
    patchTenantFormError("organisation", validateOrganisation(organisation));
  };

  const handleTenantOrganisationBlur = (organisation: string) => {
    const formatError = validateOrganisation(organisation);
    if (formatError) {
      patchTenantFormError("organisation", formatError);
      return;
    }
    patchTenantFormError("organisation", validateOrganisationUnique(organisation, tenants));
  };

  const handleTenantContactNameChange = (contact_name: string) => {
    setTenantForm((prev) => ({ ...prev, contact_name }));
    patchTenantFormError("contact_name", validateContactName(contact_name));
  };

  const handleTenantEmailChange = (email: string) => {
    setTenantForm((prev) => ({ ...prev, email }));
    emailAvailability.handleChange(email);
  };

  const handleTenantPhoneChange = (phone_number: string) => {
    setTenantForm((prev) => ({ ...prev, phone_number }));
    patchTenantFormError("phone_number", validateE164Phone(phone_number));
  };

  const canSubmitTenantForm = useMemo(() => {
    if (isSubmittingTenant || emailRegistry.isLoadingKnownEmails) return false;
    if (emailAvailability.status === "checking") return false;
    if (
      tenantForm.email.trim() &&
      !emailAvailabilityConfirmed(tenantForm.email, emailAvailability.status)
    ) {
      return false;
    }
    return (
      Object.keys(
        collectCreateTenantErrors(
          tenantForm,
          tenants,
          emailRegistry.knownTenantEmails,
          emailRegistry.knownUserEmails,
        ),
      ).length === 0
    );
  }, [
    isSubmittingTenant,
    emailRegistry.isLoadingKnownEmails,
    emailRegistry.knownTenantEmails,
    emailRegistry.knownUserEmails,
    emailAvailability.status,
    tenantForm.organisation,
    tenantForm.contact_name,
    tenantForm.email,
    tenantForm.phone_number,
    tenants,
  ]);

  return {
    isTenantModalOpen,
    tenantForm,
    setTenantForm,
    tenantFormErrors,
    setTenantFormErrors,
    isSubmittingTenant,
    openTenantModal,
    closeTenantModal,
    handleRegisterTenant,
    handleTenantOrganisationChange,
    handleTenantOrganisationBlur,
    handleTenantContactNameChange,
    handleTenantEmailChange,
    handleTenantPhoneChange,
    tenantEmailStatus: emailAvailability.status,
    canSubmitTenantForm,
  };
}
