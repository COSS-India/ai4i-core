import type { ReactNode } from "react";
import { FormHelperText, type FormHelperTextProps } from "@chakra-ui/react";

const TONE = {
  muted: "gray.500",
  success: "green.600",
  error: "red.500",
} as const;

export type FieldHintTone = keyof typeof TONE;

type FieldHintProps = {
  children?: ReactNode;
  tone?: FieldHintTone;
  show?: boolean;
} & Omit<FormHelperTextProps, "children" | "color">;

/**
 * Always-visible field guidance. Copy belongs in `FIELD_HINTS`.
 *
 * Hints add height under the input. Put fields in `FormFieldsRow` (or
 * `align="flex-start"`), never `align="flex-end"`, or shorter fields drop.
 */
export default function FieldHint({
  children,
  tone = "muted",
  show = true,
  fontSize = "xs",
  mt = 1,
  ...rest
}: FieldHintProps) {
  if (!show || children == null || children === "") return null;
  return (
    <FormHelperText fontSize={fontSize} color={TONE[tone]} m={0} mt={mt} {...rest}>
      {children}
    </FormHelperText>
  );
}
