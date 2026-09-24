import {
  FormControl,
  FormErrorMessage,
  Input,
  SimpleGrid,
  Text,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import { dash } from "../../utils/valueFormatters";

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

type InstitutionFormProps = {
  mode: InstitutionFormMode;
  values: InstitutionFormValues;
  errors?: InstitutionFormErrors;
  /** Edit only. Pending institutions can change the contact email. */
  emailEditable?: boolean;
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
};

function ReadOnlyValue({ children }: { children: React.ReactNode }) {
  return (
    <Text fontSize="md" color="ink.700" py={1}>
      {children}
    </Text>
  );
}

/** Shared Institution fields. Mode changes editability, not the field list. */
export default function InstitutionForm({
  mode,
  values,
  errors = {},
  emailEditable = false,
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

  const emailHint = (() => {
    if (isView) return null;
    if (isCreate) {
      if (emailStatus === "checking") return FIELD_HINTS.tenant.emailChecking;
      if (emailStatus === "available") return FIELD_HINTS.tenant.emailAvailable;
      return FIELD_HINTS.tenant.email.helper;
    }
    return null;
  })();

  const fields = (
    <>
      {showOrganisation || !isView ? (
      <FormControl
        isRequired={!isView}
        isInvalid={!isView && Boolean(errors.organisation)}
      >
        <FieldLabel variant={isView ? "inline" : undefined}>Organisation</FieldLabel>
        {isView ? (
          <ReadOnlyValue>{dash(values.organisation)}</ReadOnlyValue>
        ) : (
          <>
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
          </>
        )}
      </FormControl>
      ) : null}

      <FormControl
        isRequired={isCreate}
        isInvalid={!isView && Boolean(errors.contact_name)}
      >
        <FieldLabel variant={isView ? "inline" : undefined}>Contact Name</FieldLabel>
        {isView ? (
          <ReadOnlyValue>{dash(values.contact_name)}</ReadOnlyValue>
        ) : (
          <>
            <Input
              value={values.contact_name}
              onChange={(e) => onContactNameChange?.(e.target.value)}
              onBlur={
                isCreate
                  ? (e) => onContactNameBlur?.(e.target.value)
                  : undefined
              }
              placeholder={isCreate ? FIELD_HINTS.tenant.contactName.placeholder : undefined}
            />
            <FormErrorMessage>{errors.contact_name}</FormErrorMessage>
            <FieldHint show={!errors.contact_name}>
              {FIELD_HINTS.tenant.contactName.helper}
            </FieldHint>
          </>
        )}
      </FormControl>

      <FormControl
        isRequired={isCreate || (mode === "edit" && emailEditable)}
        isInvalid={
          !isView &&
          (isCreate || emailEditable) &&
          Boolean(errors.email)
        }
      >
        <FieldLabel variant={isView ? "inline" : undefined}>Email</FieldLabel>
        {isView || (mode === "edit" && !emailEditable) ? (
          <>
            <ReadOnlyValue>{dash(values.email)}</ReadOnlyValue>
            {mode === "edit" && !emailEditable ? (
              <FieldHint>{FIELD_HINTS.tenant.emailPendingOnly}</FieldHint>
            ) : null}
          </>
        ) : (
          <>
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
                <FieldHint show={!errors.email}>
                  {FIELD_HINTS.tenant.emailVerifyOnChange}
                </FieldHint>
                <FieldHint
                  show={
                    !errors.email &&
                    (emailStatus === "checking" || emailStatus === "available")
                  }
                  tone={emailStatus === "available" ? "success" : "muted"}
                >
                  {emailStatus === "checking"
                    ? FIELD_HINTS.tenant.emailChecking
                    : FIELD_HINTS.tenant.emailAvailable}
                </FieldHint>
              </>
            )}
          </>
        )}
      </FormControl>

      <FormControl isInvalid={!isView && Boolean(errors.phone_number)}>
        <FieldLabel variant={isView ? "inline" : undefined}>Phone Number</FieldLabel>
        {isView ? (
          <ReadOnlyValue>{dash(values.phone_number)}</ReadOnlyValue>
        ) : (
          <>
            <Input
              value={values.phone_number}
              onChange={(e) => onPhoneChange?.(e.target.value)}
              placeholder={isCreate ? FIELD_HINTS.tenant.phone.placeholder : undefined}
            />
            <FormErrorMessage>{errors.phone_number}</FormErrorMessage>
            <FieldHint show={!errors.phone_number}>
              {FIELD_HINTS.tenant.phone.helper}
            </FieldHint>
          </>
        )}
      </FormControl>
    </>
  );

  if (isView) {
    return (
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        {fields}
      </SimpleGrid>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {fields}
    </VStack>
  );
}
