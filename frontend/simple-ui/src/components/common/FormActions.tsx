import { Button, HStack, type StackProps } from "@chakra-ui/react";
import React from "react";

type FormActionsProps = {
  submitLabel?: string;
  cancelLabel?: string;
  onCancel?: () => void;
  onSubmit?: () => void;
  isLoading?: boolean;
  loadingText?: string;
  isDisabled?: boolean;
  /** Use `submit` when this sits inside a `<form>`. */
  submitType?: "button" | "submit";
  /** Associate a submit button that lives outside the form element (modal footer). */
  form?: string;
  hideCancel?: boolean;
  /** View-only footers: outline Close without a primary submit. */
  hideSubmit?: boolean;
  justify?: StackProps["justify"];
  pt?: StackProps["pt"];
  /** Extra outline action (e.g. Reset) between Cancel and the primary button. */
  extraLabel?: string;
  onExtra?: () => void;
};

/** Shared Cancel + primary Create/Save row for Manage create/edit forms. */
export default function FormActions({
  submitLabel,
  cancelLabel = "Cancel",
  onCancel,
  onSubmit,
  isLoading = false,
  loadingText,
  isDisabled = false,
  submitType = "button",
  form,
  hideCancel = false,
  hideSubmit = false,
  justify = "flex-end",
  pt = 2,
  extraLabel,
  onExtra,
}: FormActionsProps) {
  return (
    <HStack justify={justify} spacing={3} pt={pt} w="full">
      {!hideCancel && onCancel ? (
        <Button variant="outline" onClick={onCancel} isDisabled={isLoading}>
          {cancelLabel}
        </Button>
      ) : null}
      {extraLabel && onExtra ? (
        <Button variant="outline" onClick={onExtra} isDisabled={isLoading}>
          {extraLabel}
        </Button>
      ) : null}
      {!hideSubmit && submitLabel ? (
        <Button
          type={submitType}
          form={form}
          isLoading={isLoading}
          loadingText={loadingText}
          isDisabled={isDisabled || isLoading}
          onClick={submitType === "submit" ? undefined : onSubmit}
        >
          {submitLabel}
        </Button>
      ) : null}
    </HStack>
  );
}
