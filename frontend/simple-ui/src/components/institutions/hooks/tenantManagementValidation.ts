import { INSTITUTION } from "../../../config/constants";
import type { TenantView } from "../../../types/tenant";
import {
  validateTenantContactEmail,
  validateTenantUserEmail,
} from "../../../utils/tenantEmailValidation";
import {
  validateContactName,
  validateE164Phone,
  validateFullName,
  validateOptionalPersonName,
  validateOrganisation,
  validateOrganisationUnique,
} from "../../../utils/tenantFormValidation";

export function collectCreateTenantErrors(input: {
  organisation: string;
  contact_name: string;
  email: string;
  phone_number: string;
  tenants: TenantView[];
  knownTenantEmails: Set<string>;
  knownUserEmails: Set<string>;
}): Record<string, string> {
  const {
    organisation,
    contact_name,
    email,
    phone_number,
    tenants,
    knownTenantEmails,
    knownUserEmails,
  } = input;
  const errors: Record<string, string> = {};
  const orgError = validateOrganisation(organisation);
  if (orgError) errors.organisation = orgError;
  else {
    const dupError = validateOrganisationUnique(organisation, tenants);
    if (dupError) errors.organisation = dupError;
  }
  const contactError = validateContactName(contact_name);
  if (contactError) errors.contact_name = contactError;
  const emailError = validateTenantContactEmail(
    email,
    knownTenantEmails,
    knownUserEmails,
  );
  if (emailError) errors.email = emailError;
  const phoneError = validateE164Phone(phone_number);
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}

export function collectAddUserErrors(input: {
  lockedUserFormTenantId: string | null;
  tenant_id: string;
  full_name: string;
  email: string;
  phone_number: string;
  knownTenantEmails: Set<string>;
  knownUserEmails: Set<string>;
}): Record<string, string> {
  const {
    lockedUserFormTenantId,
    tenant_id,
    full_name,
    email,
    phone_number,
    knownTenantEmails,
    knownUserEmails,
  } = input;
  const errors: Record<string, string> = {};
  const tenantId = lockedUserFormTenantId ?? tenant_id?.trim() ?? "";
  if (!tenantId) errors.tenant_id = `${INSTITUTION} is required.`;
  const fullNameError = validateFullName(full_name);
  if (fullNameError) errors.full_name = fullNameError;
  const emailError = validateTenantUserEmail(
    email,
    knownTenantEmails,
    knownUserEmails,
  );
  if (emailError) errors.email = emailError;
  const phoneError = validateE164Phone(phone_number);
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}

export function collectEditTenantErrors(input: {
  organisation: string | undefined;
  contact_name: string | undefined;
  email: string | undefined;
  phone_number: string | undefined;
  tenant_id: string;
  tenants: TenantView[];
  isEditTenantEmailEditable: boolean;
  knownTenantEmails: Set<string>;
  knownUserEmails: Set<string>;
  editTenantEmail: string | undefined;
}): Record<string, string> {
  const {
    organisation,
    contact_name,
    email,
    phone_number,
    tenant_id,
    tenants,
    isEditTenantEmailEditable,
    knownTenantEmails,
    knownUserEmails,
    editTenantEmail,
  } = input;
  const errors: Record<string, string> = {};
  const orgError = validateOrganisation(organisation ?? "");
  if (orgError) errors.organisation = orgError;
  else {
    const dupError = validateOrganisationUnique(
      organisation ?? "",
      tenants,
      tenant_id,
    );
    if (dupError) errors.organisation = dupError;
  }
  const contactError = validateOptionalPersonName(contact_name ?? "");
  if (contactError) errors.contact_name = contactError;
  if (isEditTenantEmailEditable) {
    const emailError = validateTenantContactEmail(
      email ?? "",
      knownTenantEmails,
      knownUserEmails,
      {
        excludeTenantEmail: editTenantEmail,
        excludeUserEmail: editTenantEmail,
      },
    );
    if (emailError) errors.email = emailError;
  }
  const phoneError = validateE164Phone(phone_number ?? "");
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}

export function collectEditUserErrors(input: {
  username: string | undefined;
  full_name: string | undefined;
  phone_number: string | undefined;
}): Record<string, string> {
  const { username, full_name, phone_number } = input;
  const errors: Record<string, string> = {};
  if (!username?.trim() || username.trim().length < 3) {
    errors.username = "Username must be at least 3 characters.";
  }
  const fullNameError = validateOptionalPersonName(full_name ?? "");
  if (fullNameError) errors.full_name = fullNameError;
  const phoneError = validateE164Phone(phone_number ?? "");
  if (phoneError) errors.phone_number = phoneError;
  return errors;
}
