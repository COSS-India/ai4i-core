import { useCallback, useMemo, useState } from "react";
import * as tenantService from "../../../../../services/tenantService";
import { extractErrorInfo } from "../../../../../utils/errorHandler";
import { normalizeEmail } from "../../../../../utils/tenantEmailValidation";
import {
  setFieldError,
  validateE164Phone,
  validateOptionalPersonName,
  validateOrganisation,
  validateOrganisationUnique,
} from "../../../../../utils/tenantFormValidation";
import type { TenantView } from "../../../../../types/tenant";
import type { EditTenantFormState } from "../../../types";
import { useEmailAvailabilityField } from "../../useEmailAvailabilityField";
import type { TenantEmailRegistryState, TenantModalBaseOptions } from "./types";
import {
  collectEditTenantErrors,
  emailAvailabilityConfirmed,
} from "./tenantModalValidation";

export interface UseEditTenantModalOptions extends TenantModalBaseOptions {
  tenants: TenantView[];
  emailRegistry: TenantEmailRegistryState;
}

export function useEditTenantModal({
  toast,
  tenants,
  refreshLists,
  emailRegistry,
}: UseEditTenantModalOptions) {
  const [isEditTenantModalOpen, setIsEditTenantModalOpen] = useState(false);
  const [editTenantRow, setEditTenantRow] = useState<TenantView | null>(null);
  const [editTenantForm, setEditTenantForm] = useState<EditTenantFormState>({ tenant_id: "" });
  const [editTenantFormErrors, setEditTenantFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingEditTenant, setIsSubmittingEditTenant] = useState(false);

  const patchEditTenantFormError = useCallback((field: string, error: string | undefined) => {
    setEditTenantFormErrors((prev) => setFieldError(prev, field, error));
  }, []);

  const getEditTenantEmailCheckOptions = useCallback(
    (emailValue: string) => {
      const unchanged =
        normalizeEmail(emailValue) === normalizeEmail(editTenantRow?.email ?? "");
      return {
        mode: "tenant_contact" as const,
        tenantEmails: emailRegistry.knownTenantEmails,
        userEmails: emailRegistry.knownUserEmails,
        exclusions: {
          excludeTenantEmail: editTenantRow?.email,
          excludeUserEmail: editTenantRow?.email,
        },
        skipRemoteCheck: unchanged,
      };
    },
    [emailRegistry.knownTenantEmails, emailRegistry.knownUserEmails, editTenantRow?.email],
  );

  const emailAvailability = useEmailAvailabilityField({
    enabled: isEditTenantModalOpen,
    email: editTenantForm.email ?? "",
    patchError: patchEditTenantFormError,
    getCheckOptions: getEditTenantEmailCheckOptions,
    recheckKey: isEditTenantModalOpen ? emailRegistry.knownEmailRecheckKey : undefined,
  });

  const handleOpenEditTenant = (t: TenantView) => {
    setEditTenantRow(t);
    setEditTenantForm({
      tenant_id: t.tenant_id,
      organisation: t.organisation,
      contact_name: t.contact_name,
      email: t.email,
      phone_number: t.phone_number ?? "",
    });
    setEditTenantFormErrors({});
    emailAvailability.clear();
    setIsEditTenantModalOpen(true);
    void emailRegistry.refreshKnownAccountEmails();
  };

  const handleSaveEditTenant = async () => {
    if (!editTenantForm.tenant_id) return;
    const errors = collectEditTenantErrors(
      editTenantForm,
      editTenantRow?.email,
      tenants,
      emailRegistry.knownTenantEmails,
      emailRegistry.knownUserEmails,
    );
    delete errors.email;
    const emailOk = await emailAvailability.verifyNow();
    if (!emailOk) return;
    if (Object.keys(errors).length > 0) {
      setEditTenantFormErrors(errors);
      return;
    }
    setEditTenantFormErrors({});
    const emailChanged =
      normalizeEmail(editTenantForm.email ?? "") !== normalizeEmail(editTenantRow?.email ?? "");

    setIsSubmittingEditTenant(true);
    try {
      await tenantService.updateTenant({
        tenant_id: editTenantForm.tenant_id,
        organisation: editTenantForm.organisation,
        contact_name: editTenantForm.contact_name,
        email: editTenantForm.email,
        phone_number: editTenantForm.phone_number,
      });
      if (emailChanged) {
        toast({
          title: "Verification required",
          description:
            "A verification link was sent to the new contact email. The tenant contact email will update after it is verified.",
          status: "info",
          isClosable: true,
          duration: 8000,
        });
      } else {
        toast({ title: "Tenant updated", status: "success", isClosable: true, duration: 4000 });
      }
      setIsEditTenantModalOpen(false);
      setEditTenantRow(null);
      await refreshLists(editTenantForm.tenant_id);
    } catch (err) {
      console.error("Failed to update tenant:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingEditTenant(false);
    }
  };

  const closeEditTenantModal = () => {
    emailAvailability.clear();
    setIsEditTenantModalOpen(false);
    setEditTenantRow(null);
    setEditTenantFormErrors({});
  };

  const handleEditTenantOrganisationChange = (organisation: string) => {
    setEditTenantForm((prev) => ({ ...prev, organisation }));
    patchEditTenantFormError("organisation", validateOrganisation(organisation));
  };

  const handleEditTenantOrganisationBlur = (organisation: string) => {
    const formatError = validateOrganisation(organisation);
    if (formatError) {
      patchEditTenantFormError("organisation", formatError);
      return;
    }
    patchEditTenantFormError(
      "organisation",
      validateOrganisationUnique(organisation, tenants, editTenantForm.tenant_id),
    );
  };

  const handleEditTenantContactNameChange = (contact_name: string) => {
    setEditTenantForm((prev) => ({ ...prev, contact_name }));
    patchEditTenantFormError("contact_name", validateOptionalPersonName(contact_name));
  };

  const handleEditTenantEmailChange = (email: string) => {
    setEditTenantForm((prev) => ({ ...prev, email }));
    emailAvailability.handleChange(email);
  };

  const handleEditTenantPhoneChange = (phone_number: string) => {
    setEditTenantForm((prev) => ({ ...prev, phone_number }));
    patchEditTenantFormError("phone_number", validateE164Phone(phone_number));
  };

  const canSubmitEditTenantForm = useMemo(() => {
    if (isSubmittingEditTenant || emailRegistry.isLoadingKnownEmails) return false;
    if (emailAvailability.status === "checking") return false;
    const email = editTenantForm.email ?? "";
    if (email.trim() && !emailAvailabilityConfirmed(email, emailAvailability.status)) {
      return false;
    }
    return (
      Object.keys(
        collectEditTenantErrors(
          editTenantForm,
          editTenantRow?.email,
          tenants,
          emailRegistry.knownTenantEmails,
          emailRegistry.knownUserEmails,
        ),
      ).length === 0
    );
  }, [
    isSubmittingEditTenant,
    emailRegistry.isLoadingKnownEmails,
    emailRegistry.knownTenantEmails,
    emailRegistry.knownUserEmails,
    emailAvailability.status,
    editTenantForm.organisation,
    editTenantForm.contact_name,
    editTenantForm.email,
    editTenantForm.phone_number,
    editTenantForm.tenant_id,
    editTenantRow?.email,
    tenants,
  ]);

  return {
    isEditTenantModalOpen,
    editTenantRow,
    editTenantForm,
    setEditTenantForm,
    editTenantFormErrors,
    isSubmittingEditTenant,
    handleOpenEditTenant,
    handleSaveEditTenant,
    handleEditTenantOrganisationChange,
    handleEditTenantOrganisationBlur,
    handleEditTenantContactNameChange,
    handleEditTenantEmailChange,
    handleEditTenantPhoneChange,
    editTenantEmailStatus: emailAvailability.status,
    canSubmitEditTenantForm,
    closeEditTenantModal,
  };
}
