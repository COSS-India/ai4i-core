import { Box, FormControl, FormErrorMessage, FormLabel, HStack } from "@chakra-ui/react";
import { SEVERITIES } from "../../../../../types/alerting";
import { FORM_REQUIRED_ASTERISK } from "../../constants";
import type { DefinitionFormFieldsProps } from "./types";

const severityColors = (s: string) =>
  s === "critical"
    ? { activeBg: "red.100", activeBorder: "red.600", activeText: "red.700", hoverBg: "red.50" }
    : s === "warning"
      ? { activeBg: "yellow.100", activeBorder: "yellow.600", activeText: "yellow.700", hoverBg: "yellow.50" }
      : { activeBg: "blue.100", activeBorder: "blue.600", activeText: "blue.700", hoverBg: "blue.50" };

export default function DefinitionSeverityField({ mode, defs }: DefinitionFormFieldsProps) {
  const isCreate = mode === "create";
  const severity = isCreate ? defs.createForm.severity : (defs.updateForm.severity ?? "");
  const error = isCreate ? defs.createErrors?.severity : defs.updateErrors.severity;
  const isInvalid = isCreate ? !!defs.createErrors?.severity : Boolean(defs.updateErrors.severity);

  return (
    <FormControl isRequired isInvalid={isInvalid}>
      <FormLabel fontWeight="semibold" fontSize="sm" requiredIndicator={FORM_REQUIRED_ASTERISK}>
        Severity
      </FormLabel>
      <HStack spacing={2}>
        {SEVERITIES.map((s) => {
          const isActive = severity === s;
          const colors = severityColors(s);
          return (
            <Box
              key={s}
              as="button"
              type="button"
              flex="1"
              py={2}
              px={3}
              fontSize="sm"
              fontWeight="semibold"
              textAlign="center"
              cursor="pointer"
              borderRadius="full"
              borderWidth="2px"
              borderColor={isActive ? colors.activeBorder : "gray.200"}
              bg={isActive ? colors.activeBg : "white"}
              color={isActive ? colors.activeText : "gray.500"}
              _hover={{ bg: isActive ? colors.activeBg : colors.hoverBg, borderColor: colors.activeBorder }}
              transition="all 0.15s"
              onClick={() =>
                isCreate
                  ? defs.setCreateForm({ ...defs.createForm, severity: s })
                  : defs.setUpdateForm({ ...defs.updateForm, severity: s })
              }
              textTransform="capitalize"
            >
              {s}
            </Box>
          );
        })}
      </HStack>
      <FormErrorMessage>{error}</FormErrorMessage>
    </FormControl>
  );
}
