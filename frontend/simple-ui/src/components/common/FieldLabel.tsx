import { FormLabel, HStack, Text, type FormLabelProps, type StackProps } from "@chakra-ui/react";
import React from "react";
import InfoTip from "./InfoTip";

export type FieldLabelVariant = "form" | "inline" | "metric" | "header";

export type FieldLabelProps = {
  children: React.ReactNode;
  /** Circled-i tooltip. Icon is omitted when empty. */
  hint?: string;
  /** @deprecated Prefer `hint`. */
  tip?: string;
  /**
   * - `form` — Chakra FormLabel (default)
   * - `inline` — plain text + tip (detail views, metric cards)
   * - `metric` — uppercase metric-card label
   * - `header` — uppercase table-header weight (no FormLabel)
   */
  variant?: FieldLabelVariant;
  required?: boolean;
  spacing?: StackProps["spacing"];
  formLabelProps?: Omit<FormLabelProps, "children">;
  textProps?: React.ComponentProps<typeof Text>;
};

/**
 * Platform-wide label with an optional info tip.
 *
 * Use for form labels, table headers, metric cards, and dashboard labels.
 * When `hint` is omitted, no icon is rendered.
 */
export default function FieldLabel({
  children,
  hint,
  tip,
  variant = "form",
  required = false,
  spacing = 1.5,
  formLabelProps,
  textProps,
}: FieldLabelProps) {
  const message = hint ?? tip;
  const tipNode = message ? <InfoTip message={message} /> : null;

  if (variant === "form") {
    return (
      <FormLabel fontSize="sm" fontWeight="medium" mb={1} {...formLabelProps}>
        <HStack as="span" spacing={spacing} display="inline-flex" align="center">
          <Text as="span" color="inherit">
            {children}
            {required ? (
              <Text as="span" color="red.500" ml={0.5}>
                *
              </Text>
            ) : null}
          </Text>
          {tipNode}
        </HStack>
      </FormLabel>
    );
  }

  if (variant === "metric") {
    return (
      <HStack spacing={spacing} align="center">
        <Text
          fontSize="11.5px"
          fontWeight="700"
          color="blue.500"
          letterSpacing="0.5px"
          textTransform="uppercase"
          {...textProps}
        >
          {children}
        </Text>
        {tipNode}
      </HStack>
    );
  }

  if (variant === "header") {
    return (
      <HStack spacing={1} align="center" justify="flex-start">
        <Text as="span" color="inherit" {...textProps}>
          {children}
        </Text>
        {tipNode}
      </HStack>
    );
  }

  // inline
  return (
    <HStack spacing={spacing} align="center">
      <Text fontSize="sm" color="gray.500" {...textProps}>
        {children}
      </Text>
      {tipNode}
    </HStack>
  );
}
