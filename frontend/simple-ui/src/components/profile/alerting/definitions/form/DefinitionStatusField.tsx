import { FormControl, FormLabel, HStack, Switch, Text } from "@chakra-ui/react";
import { FORM_REQUIRED_ASTERISK } from "../../constants";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionStatusField({ mode, defs }: DefinitionFormFieldsProps) {
  const isCreate = mode === "create";
  const enabled = isCreate ? defs.createForm.enabled !== false : (defs.updateForm.enabled ?? true);

  return (
    <FormControl isRequired>
      <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
        Status
      </FormLabel>
      <HStack>
        <Switch
          isChecked={enabled}
          onChange={(e) =>
            isCreate
              ? defs.setCreateForm({ ...defs.createForm, enabled: e.target.checked })
              : defs.setUpdateForm({ ...defs.updateForm, enabled: e.target.checked })
          }
          colorScheme="green"
        />
        <Text fontSize="sm">Enable this alert</Text>
      </HStack>
    </FormControl>
  );
}
