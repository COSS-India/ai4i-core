import type { ReactNode } from "react";
import { Text, type TextProps } from "@chakra-ui/react";

const TONE = {
  muted: "gray.500",
  success: "green.600",
  error: "red.500",
} as const;

export type FieldHintTone = keyof typeof TONE;

type FieldHintProps = {
  children?: ReactNode;
  tone?: FieldHintTone;
  /** Skip render (e.g. while an error message is showing). */
  show?: boolean;
} & Omit<TextProps, "children" | "color">;

/** Always-visible field guidance. Copy belongs in `FIELD_HINTS`. */
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
    <Text fontSize={fontSize} color={TONE[tone]} m={0} mt={mt} {...rest}>
      {children}
    </Text>
  );
}
