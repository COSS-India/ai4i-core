// Left-panel request form for AI service pages

import React from "react";
import { GridItem, VStack } from "@chakra-ui/react";
import type { RequestContainerProps, ServiceInputType } from "../../types/servicePage";
import HelperText from "./HelperText";
import LanguageConfig from "./LanguageConfig";
import ServiceDropdown from "./ServiceDropdown";
import SubmitButton from "./SubmitButton";
import AudioInput from "./inputs/AudioInput";
import ImageInput from "./inputs/ImageInput";
import TextInput from "./inputs/TextInput";

const renderInput = (
  inputType: ServiceInputType | undefined,
  props: RequestContainerProps
): React.ReactNode => {
  switch (inputType) {
    case "text":
      return props.textInput ? <TextInput {...props.textInput} /> : null;
    case "audio":
      return props.audioInput ? <AudioInput {...props.audioInput} /> : null;
    case "image":
      return props.imageInput ? <ImageInput {...props.imageInput} /> : null;
    case "custom":
      return props.customInput ?? null;
    default:
      return null;
  }
};

const RequestContainer: React.FC<RequestContainerProps> = (props) => {
  const {
    serviceDropdown,
    languageConfig,
    inputType,
    helperText,
    helperItems,
    submitButton,
    children,
    topSlot,
    spacing = 6,
  } = props;

  return (
    <GridItem pt={0} mt={0} alignSelf="flex-start">
      <VStack spacing={spacing} align="stretch" pt={0} mt={0}>
        {topSlot}
        {serviceDropdown && <ServiceDropdown {...serviceDropdown} />}
        {languageConfig && <LanguageConfig {...languageConfig} />}
        {children}
        {renderInput(inputType, props)}
        <HelperText text={helperText} items={helperItems} />
        <SubmitButton {...submitButton} />
      </VStack>
    </GridItem>
  );
};

export default RequestContainer;
