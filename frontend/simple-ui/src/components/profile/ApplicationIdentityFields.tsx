import {
  Alert,
  AlertIcon,
  FormControl,
  FormErrorMessage,
  Input,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { FIELD_HINTS } from "../../config/fieldHints";
import { dash } from "../../utils/valueFormatters";
import FieldHint from "../common/FieldHint";
import FieldLabel from "../common/FieldLabel";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import type { ApplicationForm } from "./hooks/useApplicationManagement";

type ApplicationIdentityFieldsProps = {
  mode: "create" | "edit" | "view";
  form: ApplicationForm;
  setForm: React.Dispatch<React.SetStateAction<ApplicationForm>>;
  errors: Record<string, string>;
  banner: string | null;
};

/** Shared Application identity fields. Budget stays outside this component. */
export default function ApplicationIdentityFields({
  mode,
  form,
  setForm,
  errors,
  banner,
}: ApplicationIdentityFieldsProps) {
  const isView = mode === "view";

  if (isView) {
    return (
      <FormSection title="Application">
        <ReadOnlyField label="Application name">{dash(form.name)}</ReadOnlyField>
        <ReadOnlyField label="Description">{dash(form.description)}</ReadOnlyField>
        <ReadOnlyField label="Domain">{dash(form.domain)}</ReadOnlyField>
      </FormSection>
    );
  }

  return (
    <FormSection title="Application">
      {banner ? (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          {banner}
        </Alert>
      ) : null}
      <VStack spacing={4} align="stretch">
        <FormControl isRequired isInvalid={Boolean(errors.name)}>
          <FieldLabel>Application name</FieldLabel>
          <Input
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            placeholder={FIELD_HINTS.application.name.placeholder}
          />
          <FormErrorMessage>{errors.name}</FormErrorMessage>
          <FieldHint show={!errors.name}>{FIELD_HINTS.application.name.helper}</FieldHint>
        </FormControl>
        <FormControl>
          <FieldLabel>Description</FieldLabel>
          <Textarea
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
            placeholder={FIELD_HINTS.application.description.placeholder}
            rows={3}
          />
          <FieldHint>{FIELD_HINTS.application.description.helper}</FieldHint>
        </FormControl>
        <FormControl>
          <FieldLabel>Domain</FieldLabel>
          <Input
            value={form.domain}
            onChange={(e) => setForm((prev) => ({ ...prev, domain: e.target.value }))}
            placeholder={FIELD_HINTS.application.domain.placeholder}
          />
          <FieldHint>{FIELD_HINTS.application.domain.helper}</FieldHint>
        </FormControl>
      </VStack>
    </FormSection>
  );
}
