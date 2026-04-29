// PasswordRequirements — live, inline checklist of password-policy rules.
//
// Mirrors the backend's PasswordManager.validate_strength so the UI never
// drifts from the server. If a rule changes server-side, update both this
// list and the SPECIAL_CHARS constant.

import { Box, HStack, Icon, Text, VStack } from "@chakra-ui/react";
import { CheckIcon, CloseIcon } from "@chakra-ui/icons";
import React from "react";

const SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?";

export interface PasswordRule {
  label: string;
  test: (password: string) => boolean;
}

// Single source of truth for the policy. Each rule's `test` is a pure
// function from password to bool. Keep keyed-by-label so the UI doesn't
// reorder under render.
export const PASSWORD_RULES: PasswordRule[] = [
  { label: "Minimum 8 characters",          test: (p) => p.length >= 8 },
  { label: "Maximum 64 characters",         test: (p) => p.length <= 64 && p.length > 0 },
  { label: "At least one uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { label: "At least one lowercase letter", test: (p) => /[a-z]/.test(p) },
  { label: "At least one number",           test: (p) => /[0-9]/.test(p) },
  { label: "At least one special character",test: (p) => Array.from(SPECIAL_CHARS).some((c) => p.includes(c)) },
  { label: "No spaces",                     test: (p) => p.length > 0 && !/\s/.test(p) },
];

export function passwordPasses(password: string): boolean {
  return PASSWORD_RULES.every((r) => r.test(password));
}

interface Props {
  password: string;
  /** Compact layout — smaller font + tighter spacing. */
  compact?: boolean;
}

const PasswordRequirements: React.FC<Props> = ({ password, compact = false }) => {
  const empty = password.length === 0;
  const fontSize = compact ? "xs" : "sm";
  const iconSize = compact ? 2.5 : 3;

  return (
    <Box mt={1} aria-live="polite">
      <Text fontSize={fontSize} color="gray.600" mb={1}>
        Password requirements:
      </Text>
      <VStack align="start" spacing={1}>
        {PASSWORD_RULES.map((rule) => {
          const ok = !empty && rule.test(password);
          const color = empty ? "gray.400" : ok ? "green.500" : "red.500";
          return (
            <HStack key={rule.label} spacing={2} align="center">
              <Icon
                as={ok ? CheckIcon : CloseIcon}
                color={color}
                boxSize={iconSize}
              />
              <Text fontSize={fontSize} color={color}>
                {rule.label}
              </Text>
            </HStack>
          );
        })}
      </VStack>
    </Box>
  );
};

export default PasswordRequirements;
