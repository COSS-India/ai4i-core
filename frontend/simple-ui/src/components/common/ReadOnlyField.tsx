import { Box, Text } from "@chakra-ui/react";
import React from "react";
import FieldLabel from "./FieldLabel";

type ReadOnlyFieldProps = {
  label: string;
  children: React.ReactNode;
  /** Span the full form width inside a two-column grid. */
  fullWidth?: boolean;
};

/** View-mode value. Same label as an editable field, without an input chrome. */
export default function ReadOnlyField({ label, children, fullWidth }: ReadOnlyFieldProps) {
  return (
    <Box gridColumn={fullWidth ? { md: "1 / -1" } : undefined}>
      <FieldLabel variant="inline">{label}</FieldLabel>
      <Box mt={1}>
        {typeof children === "string" || typeof children === "number" ? (
          <Text fontSize="sm" color="ink.800" wordBreak="break-word">
            {children}
          </Text>
        ) : (
          children
        )}
      </Box>
    </Box>
  );
}
