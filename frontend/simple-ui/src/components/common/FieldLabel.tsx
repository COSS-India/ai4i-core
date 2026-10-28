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
  /**
   * Horizontal alignment for `header` / `metric` stacks (e.g. Actions rail → `right`).
   */
  align?: "left" | "center" | "right";
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
function stackJustify(
  align: FieldLabelProps["align"],
): NonNullable<StackProps["justify"]> {
  if (align === "right") return "flex-end";
  if (align === "center") return "center";
  return "flex-start";
}

export default function FieldLabel({
  children,
  hint,
  tip,
  variant = "form",
  align = "left",
  required = false,
  spacing = 1.5,
  formLabelProps,
  textProps,
}: Readonly<FieldLabelProps>) {
  const message = hint ?? tip;
  const tipNode = message ? <InfoTip message={message} /> : null;
  const justify = stackJustify(align);

  if (variant === "form") {
    return (
      <FormLabel fontSize="sm" fontWeight="600" mb={1} {...formLabelProps}>
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
      <HStack spacing={spacing} align="center" justify={justify} w="100%">
        <Text
          fontSize="11.5px"
          fontWeight="700"
          color="ink.500"
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
    // Right-aligned control columns (e.g. Actions) stay on one line; other
    // headers may wrap so long labels are not clipped in narrow columns.
    const nowrap = align === "right";
    return (
      <HStack spacing={1} align="center" justify={justify} w="100%" minW={0}>
        <Text
          as="span"
          color="inherit"
          whiteSpace={nowrap ? "nowrap" : "normal"}
          noOfLines={nowrap ? undefined : 2}
          title={typeof children === "string" ? children : undefined}
          {...textProps}
        >
          {children}
        </Text>
        {tipNode}
      </HStack>
    );
  }

  // inline
  return (
    <HStack spacing={spacing} align="center">
      <Text fontSize="sm" color="ink.500" {...textProps}>
        {children}
      </Text>
      {tipNode}
    </HStack>
  );
}
