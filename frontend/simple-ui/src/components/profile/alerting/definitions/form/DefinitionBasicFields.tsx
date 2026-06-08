import { FormControl, FormErrorMessage, FormLabel, Input, Textarea } from "@chakra-ui/react";
import { FORM_REQUIRED_ASTERISK } from "../../constants";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionBasicFields({ mode, defs }: DefinitionFormFieldsProps) {
  if (mode === "create") {
    return (
      <>
        <FormControl isRequired isInvalid={!!defs.createErrors?.name}>
          <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
            Alert Name
          </FormLabel>
          <Input
            placeholder="e.g. High Latency — ASR Global"
            value={defs.createForm.name}
            onChange={(e) => defs.setCreateForm({ ...defs.createForm, name: e.target.value })}
            bg="white"
          />
          <FormErrorMessage>{defs.createErrors?.name}</FormErrorMessage>
        </FormControl>
        <FormControl>
          <FormLabel fontWeight="semibold" fontSize="sm">Description</FormLabel>
          <Textarea
            placeholder="Additional context about this alert and why it exists."
            value={defs.createForm.description ?? ""}
            onChange={(e) => defs.setCreateForm({ ...defs.createForm, description: e.target.value || null })}
            bg="white"
            rows={3}
          />
        </FormControl>
      </>
    );
  }

  return (
    <>
      <FormControl>
        <FormLabel fontWeight="semibold" fontSize="sm">Name</FormLabel>
        <Input value={defs.updateItem?.name ?? ""} isReadOnly bg="gray.50" cursor="not-allowed" />
      </FormControl>
      <FormControl>
        <FormLabel fontWeight="semibold" fontSize="sm">Description</FormLabel>
        <Textarea
          value={defs.updateForm.description ?? ""}
          onChange={(e) => defs.setUpdateForm({ ...defs.updateForm, description: e.target.value || null })}
          bg="white"
          rows={3}
        />
      </FormControl>
    </>
  );
}
