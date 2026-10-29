/**
 * Sparse PATCH helpers for Edit Institution (AI4IDS-3401).
 * Only changed keys are sent — email only when the operator explicitly
 * opened Correct email (PENDING) or picked a new contact (ACTIVE).
 */

import type { TenantUpdateRequest } from "../types/tenant";
import { cleanText, normalizePhoneInput } from "./tenantFormValidation";
import { normalizeEmail } from "./tenantEmailValidation";

export type TenantEditBaseline = {
  organisation?: string | null;
  contact_name?: string | null;
  email?: string | null;
  phone_number?: string | null;
};

export type TenantEditFormValues = {
  organisation?: string;
  contact_name?: string;
  email?: string;
  phone_number?: string;
};

export type BuildTenantEditPatchOptions = {
  /** Operator opened Correct email (PENDING typed-email flow). */
  emailEditOpen?: boolean;
  /** Operator picked an Institution Admin (ACTIVE Change contact). */
  selectedContactUserId?: string;
};

function phoneKey(value: string | null | undefined): string {
  return normalizePhoneInput(value ?? "");
}

function textKey(value: string | null | undefined): string {
  return cleanText(value ?? "");
}

/**
 * Build a PATCH body with only changed fields (+ tenant_id).
 * Returns null when nothing would change on the server.
 */
export function buildTenantEditPatch(
  tenantId: string,
  baseline: TenantEditBaseline,
  form: TenantEditFormValues,
  options: BuildTenantEditPatchOptions = {},
): (TenantUpdateRequest & { tenant_id: string }) | null {
  const body: TenantUpdateRequest & { tenant_id: string } = {
    tenant_id: tenantId,
  };

  if (textKey(form.organisation) !== textKey(baseline.organisation)) {
    body.organisation = form.organisation ?? "";
  }
  if (textKey(form.contact_name) !== textKey(baseline.contact_name)) {
    body.contact_name = form.contact_name ?? "";
  }
  if (phoneKey(form.phone_number) !== phoneKey(baseline.phone_number)) {
    body.phone_number = form.phone_number ?? "";
  }

  if (options.selectedContactUserId) {
    body.contact_user_id = options.selectedContactUserId;
  } else if (options.emailEditOpen) {
    const next = normalizeEmail(form.email ?? "");
    const prev = normalizeEmail(baseline.email ?? "");
    if (next && next !== prev) {
      body.email = form.email?.trim() ?? "";
    }
  }

  const keys = Object.keys(body).filter((k) => k !== "tenant_id");
  return keys.length === 0 ? null : body;
}
