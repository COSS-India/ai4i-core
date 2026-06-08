import type { EmailAvailabilityStatus } from "../../../../../utils/tenantEmailAvailability";
import {
  validateEmailFormatOnly,
  validateTenantContactEmail,
  validateTenantUserEmail,
} from "../../../../../utils/tenantEmailValidation";
import {
  validateContactName,
  validateE164Phone,
  validateFullName,
  validateOptionalPersonName,
  validateOrganisation,
  validateOrganisationUnique,
} from "../../../../../utils/tenantFormValidation";
import type { TenantView } from "../../../../../types/tenant";
import type {
  EditTenantFormState,
  EditUserFormState,
  TenantFormState,
  TenantUserFormState,
} from "../../../types";

export function emailAvailabilityConfirmed(
  email: string,
  status: EmailAvailabilityStatus,
): boolean {
  if (!email.trim()) return false;
  if (validateEmailFormatOnly(email)) return false;
  return status === "available";
}

export function collectCreateTenantErrors(
  tenantForm: TenantFormState,
  tenants: TenantView[],
  knownTenantEmails: Set<string>,
  knownUserEmails: Set<string>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const orgError = validateOrganisation(tenantForm.organisation);
  if (orgError) errors.organisation = orgError;
  else {
    const dupError = validateOrganisationUnique(tenantForm.organisation, tenants);
    if (dupError) errors.organisation = dupError;
  }
  const contactError = validateContactName(tenantForm.contact_name);
  if (contactError) errors.contact_name = contactError;
  const emailError = validateTenantContactEmail(
    tenantForm.email,
    knownTenantEmails,
    knownUserEmails,
  );
  if (emailError) errors.email = emailError;
  const phoneError = validateE164Phone(tenantForm.phone_number);
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}

export function collectAddUserErrors(
  userForm: TenantUserFormState,
  lockedUserFormTenantId: string | null,
  knownTenantEmails: Set<string>,
  knownUserEmails: Set<string>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const tenantId = lockedUserFormTenantId ?? userForm.tenant_id?.trim() ?? "";
  if (!tenantId) errors.tenant_id = "Tenant is required.";
  const fullNameError = validateFullName(userForm.full_name);
  if (fullNameError) errors.full_name = fullNameError;
  const emailError = validateTenantUserEmail(userForm.email, knownTenantEmails, knownUserEmails);
  if (emailError) errors.email = emailError;
  const phoneError = validateE164Phone(userForm.phone_number);
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}

export function collectEditTenantErrors(
  editTenantForm: EditTenantFormState,
  editTenantRowEmail: string | undefined,
  tenants: TenantView[],
  knownTenantEmails: Set<string>,
  knownUserEmails: Set<string>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const orgError = validateOrganisation(editTenantForm.organisation ?? "");
  if (orgError) errors.organisation = orgError;
  else {
    const dupError = validateOrganisationUnique(
      editTenantForm.organisation ?? "",
      tenants,
      editTenantForm.tenant_id,
    );
    if (dupError) errors.organisation = dupError;
  }
  const contactError = validateOptionalPersonName(editTenantForm.contact_name ?? "");
  if (contactError) errors.contact_name = contactError;
  const emailError = validateTenantContactEmail(
    editTenantForm.email ?? "",
    knownTenantEmails,
    knownUserEmails,
    {
      excludeTenantEmail: editTenantRowEmail,
      excludeUserEmail: editTenantRowEmail,
    },
  );
  if (emailError) errors.email = emailError;
  const phoneError = validateE164Phone(editTenantForm.phone_number ?? "");
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}

export function collectEditUserErrors(editUserForm: EditUserFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!editUserForm.username?.trim() || editUserForm.username.trim().length < 3) {
    errors.username = "Username must be at least 3 characters.";
  }
  const fullNameError = validateOptionalPersonName(editUserForm.full_name ?? "");
  if (fullNameError) errors.full_name = fullNameError;
  const phoneError = validateE164Phone(editUserForm.phone_number ?? "");
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}
