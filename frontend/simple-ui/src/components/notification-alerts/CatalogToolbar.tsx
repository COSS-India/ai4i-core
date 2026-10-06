import { Box, Button, ButtonGroup, Checkbox, Text } from "@chakra-ui/react";
import React from "react";
import {
  RECIPIENT_ROLE_LABELS,
  SCOPE_LABELS,
  type NotificationScope,
} from "../../types/notificationAlerts";

const SCOPE_OPTIONS: NotificationScope[] = ["GLOBAL", "INSTITUTION"];

interface ScopeToggleProps {
  value: NotificationScope;
  onChange: (scope: NotificationScope) => void;
  /** Row display name, for the buttons' accessible names. */
  rowLabel: string;
}

/** Global / Institution segmented control for one catalog row. */
export const ScopeToggle: React.FC<ScopeToggleProps> = ({
  value,
  onChange,
  rowLabel,
}) => (
  <ButtonGroup size="sm" isAttached role="radiogroup" aria-label={`Scope for ${rowLabel}`}>
    {SCOPE_OPTIONS.map((scope) => {
      const selected = value === scope;
      return (
        <Button
          key={scope}
          role="radio"
          aria-checked={selected}
          onClick={() => onChange(scope)}
          colorScheme={selected ? "blue" : "gray"}
          variant={selected ? "solid" : "outline"}
          fontWeight="semibold"
        >
          {SCOPE_LABELS[scope]}
        </Button>
      );
    })}
  </ButtonGroup>
);

interface AdopterAdminCheckboxProps {
  isChecked: boolean;
  /** True on INSTITUTION rows — they never reach the Adopter Admin. */
  isDisabled: boolean;
  onChange: (checked: boolean) => void;
}

/** Whether the Adopter Admin also receives a copy (recipient_roles.ADMIN). */
export const AdopterAdminCheckbox: React.FC<AdopterAdminCheckboxProps> = ({
  isChecked,
  isDisabled,
  onChange,
}) => (
  <Box
    display="inline-flex"
    px={4}
    py={2}
    borderWidth="1px"
    borderRadius="md"
    borderColor={isDisabled ? "ink.100" : "ink.200"}
  >
    <Checkbox
      isChecked={isChecked}
      isDisabled={isDisabled}
      onChange={(e) => onChange(e.target.checked)}
    >
      <Text fontSize="sm" fontWeight="semibold">
        {RECIPIENT_ROLE_LABELS.ADMIN}
      </Text>
    </Checkbox>
  </Box>
);
