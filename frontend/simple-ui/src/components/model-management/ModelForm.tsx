import { VStack } from "@chakra-ui/react";
import React from "react";
import FormSection from "../common/FormSection";
import ModelReview, { type ModelReviewSource } from "./ModelReview";

type ModelFormProps = {
  mode: "create" | "view";
  model: ModelReviewSource | null;
  /** Create only: the JSON file picker. The JSON file remains the contract. */
  upload?: React.ReactNode;
};

/**
 * Model create is an upload. View and the post-upload review show the same
 * parsed fields. There is no field-by-field edit of the JSON.
 */
export default function ModelForm({ mode, model, upload }: ModelFormProps) {
  return (
    <VStack spacing={0} align="stretch">
      {mode === "create" ? (
        <FormSection title="Upload Model Definition">{upload}</FormSection>
      ) : null}
      {model ? (
        <FormSection title="Review Model">
          <ModelReview model={model} showStatus={mode === "view"} />
        </FormSection>
      ) : null}
    </VStack>
  );
}
