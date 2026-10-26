import {
  FormControl,
  FormErrorMessage,
  Input,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import { dash } from "../../utils/valueFormatters";
import InstitutionContactEmail from "./InstitutionContactEmail";

export type InstitutionFormMode = "create" | "edit" | "view";

export type InstitutionFormValues = {
  organisation: string;
  contact_name: string;
  email: string;
  phone_number: string;
};

export type InstitutionFormErrors = Partial<
  Record<keyof InstitutionFormValues, string>
>;

type InstitutionFormProps = Readonly<{
  mode: InstitutionFormMode;
  values: InstitutionFormValues;
  errors?: InstitutionFormErrors;
  /** Edit only. Contact email editable for PENDING/ACTIVE (AI4IDS-3401). */
  emailEditable?: boolean;
  /** Pending verification address from GET/PATCH (shown in view + locked edit). */
  pendingEmail?: string | null;
  emailStatus?: string;
  onOrganisationChange?: (value: string) => void;
  onOrganisationBlur?: (value: string) => void;
  onContactNameChange?: (value: string) => void;
  onContactNameBlur?: (value: string) => void;
  onEmailChange?: (value: string) => void;
  onEmailBlur?: () => void;
  onPhoneChange?: (value: string) => void;
  /** View pages that already title the record with the organisation name. */
  showOrganisation?: boolean;
}>;

type EditableEmailFieldProps = Readonly<{
  isCreate: boolean;
  emailEditable: boolean;
  values: InstitutionFormValues;
  errors: InstitutionFormErrors;
  pendingEmail: string | null;
  emailStatus?: string;
  emailHint: string | null;
  onEmailChange?: (value: string) => void;
  onEmailBlur?: () => void;
}>;

function resolveCreateEmailHint(emailStatus?: string): string {
  if (emailStatus === "checking") return FIELD_HINTS.tenant.emailChecking;
  if (emailStatus === "available") return FIELD_HINTS.tenant.emailAvailable;
  return FIELD_HINTS.tenant.email.helper;
}

function InstitutionViewFields({
  values,
  pendingEmail,
  showOrganisation,
}: Readonly<{
  values: InstitutionFormValues;
  pendingEmail: string | null;
  showOrganisation: boolean;
}>) {
  return (
    <FormSection title="Institution">
      {showOrganisation ? (
        <ReadOnlyField label="Organisation">{dash(values.organisation)}</ReadOnlyField>
      ) : null}
      <ReadOnlyField label="Contact Name">{dash(values.contact_name)}</ReadOnlyField>
      <ReadOnlyField label="Email">
        <InstitutionContactEmail
          email={values.email}
          pendingEmail={pendingEmail}
        />
      </ReadOnlyField>
      <ReadOnlyField label="Phone Number">{dash(values.phone_number)}</ReadOnlyField>
    </FormSection>
  );
}

function InstitutionEditableEmailField({
  isCreate,
  emailEditable,
  values,
  errors,
  pendingEmail,
  emailStatus,
  emailHint,
  onEmailChange,
  onEmailBlur,
}: EditableEmailFieldProps) {
  if (!isCreate && !emailEditable) {
    return (
      <FormControl>
        <ReadOnlyField label="Email">
          <InstitutionContactEmail
            email={values.email}
            pendingEmail={pendingEmail}
          />
        </ReadOnlyField>
        <FieldHint>{FIELD_HINTS.tenant.emailPendingOnly}</FieldHint>
      </FormControl>
    );
  }

  const pendingHint = pendingEmail?.trim()
    ? `${pendingEmail.trim()} — ${FIELD_HINTS.tenant.emailVerificationPending}`
    : null;
  const showAvailabilityHint =
    !errors.email &&
    (emailStatus === "checking" || emailStatus === "available");

  return (
    <FormControl
      isRequired={isCreate || emailEditable}
      isInvalid={Boolean(errors.email)}
    >
      <FieldLabel>Email</FieldLabel>
      <Input
        type="email"
        value={values.email}
        onChange={(e) => onEmailChange?.(e.target.value)}
        onBlur={isCreate ? onEmailBlur : undefined}
        placeholder={isCreate ? FIELD_HINTS.tenant.email.placeholder : undefined}
      />
      <FormErrorMessage>{errors.email}</FormErrorMessage>
      {isCreate ? (
        <FieldHint
          show={!errors.email}
          tone={emailStatus === "available" ? "success" : "muted"}
        >
          {emailHint}
        </FieldHint>
      ) : (
        <>
          {pendingHint ? (
            <FieldHint show={!errors.email}>{pendingHint}</FieldHint>
          ) : null}
          <FieldHint show={!errors.email}>
            {FIELD_HINTS.tenant.emailVerifyOnChange}
          </FieldHint>
          <FieldHint
            show={showAvailabilityHint}
            tone={emailStatus === "available" ? "success" : "muted"}
          >
            {emailStatus === "checking"
              ? FIELD_HINTS.tenant.emailChecking
              : FIELD_HINTS.tenant.emailAvailable}
          </FieldHint>
        </>
      )}
    </FormControl>
  );
}

/** Shared Institution fields. Mode changes editability, not the field list. */
export default function InstitutionForm({
  mode,
  values,
  errors = {},
  emailEditable = false,
  pendingEmail = null,
  emailStatus,
  onOrganisationChange,
  onOrganisationBlur,
  onContactNameChange,
  onContactNameBlur,
  onEmailChange,
  onEmailBlur,
  onPhoneChange,
  showOrganisation = true,
}: InstitutionFormProps) {
  const isView = mode === "view";
  const isCreate = mode === "create";

  if (isView) {
    return (
      <InstitutionViewFields
        values={values}
        pendingEmail={pendingEmail}
        showOrganisation={showOrganisation}
      />
    );
  }

  const emailHint = isCreate ? resolveCreateEmailHint(emailStatus) : null;

  return (
    <FormSection title="Institution">
      <VStack spacing={4} align="stretch">
        <FormControl isRequired isInvalid={Boolean(errors.organisation)}>
          <FieldLabel>Organisation</FieldLabel>
          <Input
            value={values.organisation}
            onChange={(e) => onOrganisationChange?.(e.target.value)}
            onBlur={(e) => onOrganisationBlur?.(e.target.value)}
            placeholder={isCreate ? FIELD_HINTS.tenant.organisation.placeholder : undefined}
            maxLength={100}
          />
          <FormErrorMessage>{errors.organisation}</FormErrorMessage>
          <FieldHint show={!errors.organisation}>
            {FIELD_HINTS.tenant.organisation.helper}
          </FieldHint>
        </FormControl>

        <FormControl isRequired={isCreate} isInvalid={Boolean(errors.contact_name)}>
          <FieldLabel>Contact Name</FieldLabel>
          <Input
            value={values.contact_name}
            onChange={(e) => onContactNameChange?.(e.target.value)}
            onBlur={
              isCreate ? (e) => onContactNameBlur?.(e.target.value) : undefined
            }
            placeholder={isCreate ? FIELD_HINTS.tenant.contactName.placeholder : undefined}
          />
          <FormErrorMessage>{errors.contact_name}</FormErrorMessage>
          <FieldHint show={!errors.contact_name}>
            {FIELD_HINTS.tenant.contactName.helper}
          </FieldHint>
        </FormControl>

        <InstitutionEditableEmailField
          isCreate={isCreate}
          emailEditable={emailEditable}
          values={values}
          errors={errors}
          pendingEmail={pendingEmail}
          emailStatus={emailStatus}
          emailHint={emailHint}
          onEmailChange={onEmailChange}
          onEmailBlur={onEmailBlur}
        />

        <FormControl isInvalid={Boolean(errors.phone_number)}>
          <FieldLabel>Phone Number</FieldLabel>
          <Input
            value={values.phone_number}
            onChange={(e) => onPhoneChange?.(e.target.value)}
            placeholder={isCreate ? FIELD_HINTS.tenant.phone.placeholder : undefined}
          />
          <FormErrorMessage>{errors.phone_number}</FormErrorMessage>
          <FieldHint show={!errors.phone_number}>
            {FIELD_HINTS.tenant.phone.helper}
          </FieldHint>
        </FormControl>
      </VStack>
    </FormSection>
  );
}
