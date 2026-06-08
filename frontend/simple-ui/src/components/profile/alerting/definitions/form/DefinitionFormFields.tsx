import { Divider, VStack } from "@chakra-ui/react";
import DefinitionBasicFields from "./DefinitionBasicFields";
import DefinitionClassificationFields from "./DefinitionClassificationFields";
import DefinitionSeverityField from "./DefinitionSeverityField";
import DefinitionStatusField from "./DefinitionStatusField";
import DefinitionTargetField from "./DefinitionTargetField";
import DefinitionThresholdField from "./DefinitionThresholdField";
import DefinitionTimingFields from "./DefinitionTimingFields";
import type { DefinitionFormFieldsProps } from "./types";

export default function DefinitionFormFields(props: DefinitionFormFieldsProps) {
  const isCreate = props.mode === "create";

  return (
    <VStack spacing={5} align="stretch">
      <DefinitionBasicFields {...props} />
      <Divider />
      <DefinitionClassificationFields {...props} />
      {isCreate && <Divider />}
      <DefinitionTargetField {...props} />
      <Divider />
      <DefinitionThresholdField {...props} />
      <Divider />
      <DefinitionSeverityField {...props} />
      <Divider />
      <DefinitionTimingFields {...props} />
      <Divider />
      <DefinitionStatusField {...props} />
    </VStack>
  );
}
