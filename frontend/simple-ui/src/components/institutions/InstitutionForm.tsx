import {
  Box,
  Button,
  FormControl,
  FormErrorMessage,
  Input,
  Select,
  Tooltip,
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

/** Other Institution Admins who can become the contact (AI4IDS-3401). */
export type InstitutionContactChange = {
  disabled: boolean;
  /** Why the control is unavailable, or the picker hint while it is open. */
  helper: string | null;
  open: boolean;
  admins: ReadonlyArray<{ userId: string; label: string }>;
  selectedUserId: string;
  onOpen: () => void;
  onSelect: (userId: string) => void;
  onCancel: () => void;
};

/**
 * Opt-in typed email correction for PENDING institutions awaiting
 * verification (AI4IDS-3401). Email is not in the PATCH until this is open
 * and the address actually changes.
 */
export type InstitutionEmailEdit = {
  open: boolean;
  onOpen: () => void;
  onCancel: () => void;
};

type InstitutionFormProps = Readonly<{
  mode: InstitutionFormMode;
  values: InstitutionFormValues;
  errors?: InstitutionFormErrors;
  /**
   * Edit only. When true with `emailEdit`, shows Correct email (PENDING).
   * Free-text email stays off for ACTIVE — use `contactChange` instead.
   */
  emailEditable?: boolean;
  /** Edit only. Locked email + Correct email for PENDING tenants. */
  emailEdit?: InstitutionEmailEdit;
  /** Edit only. Read-only email plus Change contact. */
  contactChange?: InstitutionContactChange;
  /** Keeps the email input mounted but non-editable (e.g. while submit awaits). */
  emailDisabled?: boolean;
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
  /** Extra view-only fields kept in the Institution section. */
  children?: React.ReactNode;
}>;

type EditableEmailFieldProps = Readonly<{
  isCreate: boolean;
  emailEditable: boolean;
  emailDisabled?: boolean;
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

function emailAvailabilityTone(
  emailStatus?: string,
): "success" | "muted" {
  if (emailStatus === "available") return "success";
  return "muted";
}

function emailAvailabilityLabel(emailStatus?: string): string {
  if (emailStatus === "checking") return FIELD_HINTS.tenant.emailChecking;
  return FIELD_HINTS.tenant.emailAvailable;
}

function formatPendingEmailHint(pendingEmail: string | null): string | null {
  const pending = pendingEmail?.trim();
  if (pending) {
    return `${pending} — ${FIELD_HINTS.tenant.emailVerificationPending}`;
  }
  return null;
}

function InstitutionViewFields({
  values,
  pendingEmail,
  showOrganisation,
  children,
}: Readonly<{
  values: InstitutionFormValues;
  pendingEmail: string | null;
  showOrganisation: boolean;
  children?: React.ReactNode;
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
      {children}
    </FormSection>
  );
}

function InstitutionLockedEmailField({
  email,
  pendingEmail,
}: Readonly<{ email: string; pendingEmail: string | null }>) {
  return (
    <FormControl>
      <ReadOnlyField label="Email">
        <InstitutionContactEmail email={email} pendingEmail={pendingEmail} />
      </ReadOnlyField>
      <FieldHint>{FIELD_HINTS.tenant.emailPendingOnly}</FieldHint>
    </FormControl>
  );
}

function InstitutionChangeContactField({
  email,
  pendingEmail,
  contactChange,
}: Readonly<{
  email: string;
  pendingEmail: string | null;
  contactChange: InstitutionContactChange;
}>) {
  return (
    <FormControl>
      <ReadOnlyField label="Email">
        <InstitutionContactEmail email={email} pendingEmail={pendingEmail} />
      </ReadOnlyField>
      {contactChange.open && !contactChange.disabled ? (
        <VStack align="stretch" spacing={2} mt={2}>
          <Select
            size="sm"
            aria-label={FIELD_HINTS.tenant.contactChangeSelect}
            placeholder={FIELD_HINTS.tenant.contactChangeSelect}
            value={contactChange.selectedUserId}
            onChange={(e) => contactChange.onSelect(e.target.value)}
          >
            {contactChange.admins.map((admin) => (
              <option key={admin.userId} value={admin.userId}>
                {admin.label}
              </option>
            ))}
          </Select>
          <Button
            size="sm"
            variant="link"
            colorScheme="blue"
            alignSelf="flex-start"
            onClick={contactChange.onCancel}
          >
            Cancel
          </Button>
        </VStack>
      ) : (
        <Tooltip
          label={contactChange.helper}
          placement="top"
          hasArrow
          openDelay={300}
          isDisabled={!contactChange.helper}
        >
          {/* Disabled buttons swallow hover — wrap so the reason still shows. */}
          <Box as="span" display="inline-block" mt={1} alignSelf="flex-start">
            <Button
              size="sm"
              variant="link"
              colorScheme="blue"
              isDisabled={contactChange.disabled}
              onClick={contactChange.onOpen}
            >
              {FIELD_HINTS.tenant.contactChange}
            </Button>
          </Box>
        </Tooltip>
      )}
      <FieldHint show={contactChange.open && Boolean(contactChange.helper)}>
        {contactChange.helper}
      </FieldHint>
    </FormControl>
  );
}

function InstitutionCorrectEmailField({
  values,
  errors,
  pendingEmail,
  emailStatus,
  emailDisabled,
  emailEdit,
  onEmailChange,
}: Readonly<{
  values: InstitutionFormValues;
  errors: InstitutionFormErrors;
  pendingEmail: string | null;
  emailStatus?: string;
  emailDisabled?: boolean;
  emailEdit: InstitutionEmailEdit;
  onEmailChange?: (value: string) => void;
}>) {
  if (emailEdit.open) {
    return (
      <FormControl isRequired isInvalid={Boolean(errors.email)}>
        <FieldLabel hint={FIELD_HINTS.tenant.email.tip}>Email</FieldLabel>
        <Input
          type="email"
          value={values.email}
          isDisabled={emailDisabled}
          onChange={(e) => onEmailChange?.(e.target.value)}
        />
        <FormErrorMessage>{errors.email}</FormErrorMessage>
        <EditEmailHints
          errors={errors}
          pendingEmail={pendingEmail}
          emailStatus={emailStatus}
        />
        <Button
          size="sm"
          variant="link"
          colorScheme="blue"
          alignSelf="flex-start"
          mt={1}
          isDisabled={emailDisabled}
          onClick={emailEdit.onCancel}
        >
          Cancel
        </Button>
      </FormControl>
    );
  }

  return (
    <FormControl>
      <ReadOnlyField label="Email">
        <InstitutionContactEmail
          email={values.email}
          pendingEmail={pendingEmail}
        />
      </ReadOnlyField>
      <Tooltip
        label={FIELD_HINTS.tenant.emailEditHint}
        placement="top"
        hasArrow
        openDelay={300}
      >
        <Box as="span" display="inline-block" mt={1} alignSelf="flex-start">
          <Button
            size="sm"
            variant="link"
            colorScheme="blue"
            isDisabled={emailDisabled}
            onClick={emailEdit.onOpen}
          >
            {FIELD_HINTS.tenant.emailEdit}
          </Button>
        </Box>
      </Tooltip>
      <FieldHint>{FIELD_HINTS.tenant.emailPendingOnly}</FieldHint>
    </FormControl>
  );
}

function CreateEmailHints({
  errors,
  emailStatus,
  emailHint,
}: Readonly<{
  errors: InstitutionFormErrors;
  emailStatus?: string;
  emailHint: string | null;
}>) {
  return (
    <FieldHint
      show={!errors.email}
      tone={emailAvailabilityTone(emailStatus)}
    >
      {emailHint}
    </FieldHint>
  );
}

function EditEmailHints({
  errors,
  pendingEmail,
  emailStatus,
}: Readonly<{
  errors: InstitutionFormErrors;
  pendingEmail: string | null;
  emailStatus?: string;
}>) {
  const pendingHint = formatPendingEmailHint(pendingEmail);
  const showAvailabilityHint =
    !errors.email &&
    (emailStatus === "checking" || emailStatus === "available");

  return (
    <>
      {pendingHint ? (
        <FieldHint show={!errors.email}>{pendingHint}</FieldHint>
      ) : null}
      <FieldHint show={!errors.email}>
        {FIELD_HINTS.tenant.emailVerifyOnChange}
      </FieldHint>
      <FieldHint
        show={showAvailabilityHint}
        tone={emailAvailabilityTone(emailStatus)}
      >
        {emailAvailabilityLabel(emailStatus)}
      </FieldHint>
    </>
  );
}

function InstitutionEditableEmailField({
  isCreate,
  emailEditable,
  emailDisabled = false,
  values,
  errors,
  pendingEmail,
  emailStatus,
  emailHint,
  onEmailChange,
  onEmailBlur,
}: EditableEmailFieldProps) {
  const canEditEmail = isCreate || emailEditable;
  if (canEditEmail) {
    return (
      <FormControl isRequired isInvalid={Boolean(errors.email)}>
        <FieldLabel hint={FIELD_HINTS.tenant.email.tip}>Email</FieldLabel>
        <Input
          type="email"
          value={values.email}
          isDisabled={emailDisabled}
          onChange={(e) => onEmailChange?.(e.target.value)}
          onBlur={isCreate ? onEmailBlur : undefined}
          placeholder={
            isCreate ? FIELD_HINTS.tenant.email.placeholder : undefined
          }
        />
        <FormErrorMessage>{errors.email}</FormErrorMessage>
        {isCreate ? (
          <CreateEmailHints
            errors={errors}
            emailStatus={emailStatus}
            emailHint={emailHint}
          />
        ) : (
          <EditEmailHints
            errors={errors}
            pendingEmail={pendingEmail}
            emailStatus={emailStatus}
          />
        )}
      </FormControl>
    );
  }

  return (
    <InstitutionLockedEmailField
      email={values.email}
      pendingEmail={pendingEmail}
    />
  );
}

/** Shared Institution fields. Mode changes editability, not the field list. */
export default function InstitutionForm({
  mode,
  values,
  errors = {},
  emailEditable = false,
  emailEdit,
  emailDisabled = false,
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
  contactChange,
  children,
}: InstitutionFormProps) {
  const isView = mode === "view";
  const isCreate = mode === "create";

  if (isView) {
    return (
      <InstitutionViewFields
        values={values}
        pendingEmail={pendingEmail}
        showOrganisation={showOrganisation}
      >
        {children}
      </InstitutionViewFields>
    );
  }

  const emailHint = isCreate ? resolveCreateEmailHint(emailStatus) : null;

  let emailField: React.ReactNode;
  if (isCreate) {
    emailField = (
      <InstitutionEditableEmailField
        isCreate
        emailEditable
        emailDisabled={emailDisabled}
        values={values}
        errors={errors}
        pendingEmail={pendingEmail}
        emailStatus={emailStatus}
        emailHint={emailHint}
        onEmailChange={onEmailChange}
        onEmailBlur={onEmailBlur}
      />
    );
  } else if (emailEditable && emailEdit) {
    emailField = (
      <InstitutionCorrectEmailField
        values={values}
        errors={errors}
        pendingEmail={pendingEmail}
        emailStatus={emailStatus}
        emailDisabled={emailDisabled}
        emailEdit={emailEdit}
        onEmailChange={onEmailChange}
      />
    );
  } else if (contactChange) {
    emailField = (
      <InstitutionChangeContactField
        email={values.email}
        pendingEmail={pendingEmail}
        contactChange={contactChange}
      />
    );
  } else {
    emailField = (
      <InstitutionLockedEmailField
        email={values.email}
        pendingEmail={pendingEmail}
      />
    );
  }

  return (
    <FormSection title="Institution">
      <VStack spacing={4} align="stretch">
        <FormControl isRequired isInvalid={Boolean(errors.organisation)}>
          <FieldLabel hint={FIELD_HINTS.tenant.organisation.tip}>Organisation</FieldLabel>
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
          <FieldLabel hint={FIELD_HINTS.tenant.contactName.tip}>Contact Name</FieldLabel>
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

        {emailField}

        <FormControl isInvalid={Boolean(errors.phone_number)}>
          <FieldLabel hint={FIELD_HINTS.tenant.phone.tip}>Phone Number</FieldLabel>
          <Input
            value={values.phone_number}
            onChange={(e) => onPhoneChange?.(e.target.value)}
            placeholder={isCreate ? FIELD_HINTS.tenant.phone.placeholder : undefined}
          />
          <FormErrorMessage>{errors.phone_number}</FormErrorMessage>
        </FormControl>
      </VStack>
    </FormSection>
  );
}
