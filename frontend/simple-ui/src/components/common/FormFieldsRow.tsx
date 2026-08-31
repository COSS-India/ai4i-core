import { HStack, type StackProps } from "@chakra-ui/react";

/**
 * Horizontal group of form / filter fields.
 *
 * Always top-aligns. `align="flex-end"` on a field row is what breaks
 * Create Tier–style layouts: FieldHint (or an error) makes some columns
 * taller, and flex-end then drops the shorter controls (label + input)
 * to the bottom.
 *
 * Unlabeled actions (icon buttons, "Clear") should sit in this row with
 * `pt={FORM_LABEL_TO_INPUT_PT}` so they line up with the inputs, not the labels.
 */
export const FORM_LABEL_TO_INPUT_PT = 6;

export default function FormFieldsRow({
  align = "flex-start",
  flexWrap = "wrap",
  spacing = 3,
  rowGap = 3,
  ...rest
}: StackProps) {
  return (
    <HStack
      align={align}
      flexWrap={flexWrap}
      spacing={spacing}
      rowGap={rowGap}
      {...rest}
    />
  );
}
